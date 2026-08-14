from prometheus_client import Counter, Gauge, Histogram

AUCTIONS_MONITORED = Gauge(
    "auctions_monitored_total", "Аукционы под активным мониторингом"
)
ACTIVE_WORKERS = Gauge("active_workers", "Число запущенных worker-процессов")

YAHOO_REQUESTS_TOTAL = Counter(
    "yahoo_requests_total", "Всего запросов к Yahoo", ["status"]
)
YAHOO_REQUEST_ERRORS_TOTAL = Counter(
    "yahoo_request_errors_total", "Ошибки запросов к Yahoo", ["type"]
)
YAHOO_RESPONSE_LATENCY = Histogram(
    "yahoo_response_latency_seconds",
    "Латентность ответов Yahoo",
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

PAGE_DATA_PARSE_ERRORS = Counter(
    "page_data_parse_errors_total", "Ошибки парсинга pageData", ["reason"]
)

NOTIFICATIONS_SENT = Counter(
    "notifications_sent_total", "Отправленные уведомления", ["kind"]
)
NOTIFICATIONS_FAILED = Counter(
    "notifications_failed_total", "Проваленные уведомления", ["kind"]
)

POLLING_JOBS_TOTAL = Counter("polling_jobs_total", "Запущенные poll jobs", ["result"])
POLLING_JOBS_FAILED = Counter("polling_jobs_failed_total", "Проваленные poll jobs")

TELEGRAM_SEND_ERRORS = Counter(
    "telegram_send_errors_total", "Ошибки отправки в Telegram", ["type"]
)

QUEUE_SIZE = Gauge("queue_size", "Размер очереди задач ARQ", ["queue"])

REDIS_ERRORS = Counter("redis_errors_total", "Ошибки Redis")
DB_ERRORS = Counter("db_errors_total", "Ошибки PostgreSQL")
