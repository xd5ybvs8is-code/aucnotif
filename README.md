# AukNotif — Telegram-бот мониторинга Yahoo Auctions Japan

Бот принимает ссылку на аукцион Yahoo Auctions Japan, отслеживает его и присылает
уведомления о новых ставках, продлениях и скором окончании.

Ключевое свойство архитектуры: **один аукцион опрашивается ровно один раз**,
даже если за ним следят десятки пользователей. Опрос → diff → fan-out уведомлений.

## Архитектура

```text
                        ┌─────────────────────────────────────────────┐
                        │           PostgreSQL (источник истины)      │
                        │ users · auctions · user_auctions            │
                        │ auction_snapshots · sent_notifications      │
                        └──────────────▲───────────────▲──────────────┘
                                       │               │
  Telegram ◄─► Bot (aiogram)          │               │  Scheduler (1 процесс)
       │  URL → AuctionService ───────┘               │  due-аукционы → enqueue
       │                                               │
  ┌────┴────┐        ┌───────────┐   Redis (ARQ) ──► Worker × N (ARQ)
  │ FastAPI │        │ Redis     │    poll_job ──► lock ──► YahooAuctionProvider
  │ /health │        │ lock·rlimit│   (httpx, rate-limited)
  │ /metrics│        └───────────┘           │
  └─────────┘                                ▼
                                 AuctionState → Diff → Snapshot
                                                        │
                                 NotificationEngine (dedup keys)
                                                        │
                                 send_job → TelegramSender (retry)
```

- **Bot и API — разные процессы, один пакет `app/`** — масштабируются и рестартуют независимо.
- **Worker** масштабируется горизонтально; distributed lock
  `auction:{id}:poll-lock` (TTL + token-safe release) гарантирует, что аукцион
  никогда не опрашивается двумя workers одновременно.
- **Scheduler** — stateless: сканирует `next_poll_at` в PostgreSQL, поэтому
  после рестарта система восстанавливается без in-memory состояния.

## Стек

| Компонент | Выбор | Почему |
|---|---|---|
| Python | 3.12 | async-экосистема |
| Bot | aiogram 3.x (long polling) | стандарт, async-native |
| API | FastAPI | `/health`, `/ready`, `/metrics` |
| Queue | **ARQ** (не Celery) | нативно asyncio, лёгкий, cron/retry из коробки |
| DB | PostgreSQL + SQLAlchemy 2.x async + Alembic | уникальные индексы = защита от дублей |
| Cache/locks | Redis | lock, глобальный rate limiter, очередь |
| HTTP | httpx | пул соединений, timeout, единый async-стек |
| Метрики | prometheus-client | Pull на `/metrics` |
| Sentry | optional | включается `SENTRY_DSN` |

## Запуск (Docker Compose)

```bash
cp .env.example .env
# отредактируйте TELEGRAM_BOT_TOKEN в .env
docker compose up -d --build
```

Сервисы: `postgres`, `redis`, `migrate` (Alembic), `api`, `bot`, `scheduler`, `worker` (2 реплики).

## Локальная разработка

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

# нужны PostgreSQL и Redis; env — в .env или переменных окружения
alembic upgrade head
python -m app.main_bot          # бот
python -m app.main_scheduler    # scheduler
arq app.workers.settings.WorkerSettings   # worker
python -m app.main_api          # API :8000

pytest                          # unit-тесты
ruff check app tests            # lint
```

Интеграционные тесты требуют PostgreSQL: `TEST_DATABASE_URL=postgresql+asyncpg://...`
(иначе пропускаются). Для быстрой smoke-проверки работает и
`TEST_DATABASE_URL=sqlite+aiosqlite:///test.db`.

## Основные переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | токен бота (обязателен) |
| `DATABASE_URL` / `REDIS_URL` | локальные | подключения |
| `DEFAULT_TIMEZONE` | `Europe/London` | TZ новых пользователей |
| `YAHOO_RATE_LIMIT` | `1.0` | глобальный лимит запросов к Yahoo, req/s |
| `YAHOO_REQUEST_TIMEOUT` | `15` | timeout HTTP, сек |
| `POLL_INTERVAL_*` | adaptive | интервалы по бакетам времени до конца |
| `NOTIFY_*_BEFORE_SECONDS` | 1800/900/300 | пороги 30/15/5 минут |
| `STORE_RAW_DATA` | `false` | хранить raw pageData в snapshots |
| `SENTRY_DSN` | — | опционально |

## Ключевые проектные решения

### Идемпотентность уведомлений

Каждое уведомление = строка `sent_notifications` с уникальным ключом
`(user_auction_id, kind, dedup_key)`. Заявка создаётся через
INSERT + SAVEPOINT (конфликт → уведомление уже есть → пропуск).

- Timed (30/15/5 мин): `dedup_key = end_time` → **продление аукциона создаёт
  новый цикл окончания**, старые уведомления не повторяются.
- Change/extension/closed: `dedup_key = snapshot_id`.

Рестарт/retry/повторная доставка в очередь не создают дублей: отправщик
проверяет статус, scheduler периодически перепоставляет зависшие `pending`.

### Adaptive polling

Интервал опроса растёт по мере приближения `end_time` (все интервалы — в конфиге):

| До конца | Интервал |
|---|---|
| > 24ч | 6ч |
| 6–24ч | 30м |
| 1–6ч | 10м |
| 30–60м | 2м |
| < 15м | 1м |

Timed-уведомления срабатывают, только если момент `end_time - T` попал между
предыдущим и текущим опросом — никакого спама и повторных отправок.

### Продление аукциона (auto-extension)

`end_time` — это просто состояние. Изменение `end_time` обнаруживается diff'ом,
сохраняется новый snapshot, обновляется `auctions.end_time`, все дальнейшие
уведомления считаются от нового `end_time`.

### Защита от duplicate polling

- Redis lock с TTL: умерший worker освобождает лок по истечении TTL.
- Scheduler двигает `next_poll_at` на время lock TTL при enqueue.
- Глобальный rate limiter (token bucket в Redis) — общий бюджет на всех workers.

## Обработка ошибок

- HTTP 403/429/5xx/timeout → exponential backoff (configurable), счётчик ошибок,
  остановка мониторинга после N подряд.
- CAPTCHA/anti-bot → **остановка мониторинга + метрика** (обход не реализуем).
- Аукцион удалён (404/410) → остановка.
- pageData отсутствует/повреждён → error metric, backoff, никакой мусорной записи.
- Telegram API: retry с backoff, flood-control (`retry_after`) учитывается.

## ASSUMPTIONS (проверить на реальных данных)

1. `newBid` — «новая ставка с последнего просмотра страницы»; вторичный сигнал,
   истина — сравнение snapshots.
2. Yahoo продлевает аукцион на +5 минут при ставке в последние 5 минут
   (проверяется по логам пар `end_time`/`bid_count`).
3. `endtime` в формате `%Y-%m-%d %H:%M:%S` в Asia/Tokyo (парсер толерантен).
4. `winPrice` = цена моментальной продажи (Buy It Now), **не** цена победителя.

## Структура

```text
app/
├── main_bot.py / main_api.py / main_scheduler.py   # entrypoints
├── config.py · db.py
├── models/          # SQLAlchemy
├── schemas/         # Pydantic: PageData, YahooAuctionData
├── domain/          # ЧИСТАЯ логика: AuctionState, Diff, polling, notification rules, time
├── providers/yahoo/ # client (httpx+rate limit), extractor, provider
├── repositories/    # users, auctions, user_auctions, snapshots, notifications
├── services/        # auction_service, monitoring_service (application layer)
├── notifications/   # engine (claim), renderer (HTML), sender (retry)
├── workers/         # ARQ tasks + WorkerSettings
├── scheduler/       # due-scan + recovery
├── bot/             # aiogram handlers
├── api/             # FastAPI: /health /ready /metrics
└── infrastructure/  # redis, locks, rate limit, metrics, logging
```
