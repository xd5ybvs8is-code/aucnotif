from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notifications import NotificationDecision, dedup_key_for
from app.models import User, UserAuction
from app.notifications.renderer import NotificationRenderer
from app.repositories.notifications import NotificationRepository


class NotificationEngine:
    """Создаёт идемпотентные записи уведомлений для fan-out.

    Для каждого (пользователь, решение) вставляется строка sent_notifications
    с уникальным ключом (user_auction, kind, dedup_key). Текст рендерится сразу
    в timezone пользователя и сохраняется — worker отправки не зависит от
    состояния аукциона и безопасен при рестартах.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = NotificationRepository(session)

    async def create_jobs(
        self,
        decisions: list[NotificationDecision],
        watchers: list[tuple[User, UserAuction]],
        snapshot_id: int,
        url: str,
    ) -> list[int]:
        """Возвращает id созданных (заявленных) уведомлений для enqueue."""
        created: list[int] = []
        for user, link in watchers:
            renderer = NotificationRenderer(user.timezone)
            for decision in decisions:
                key = dedup_key_for(decision, snapshot_id)
                row = await self._repo.claim(link.id, decision.kind.value, key)
                if row is None:
                    continue
                row.text = renderer.render(decision, url)
                created.append(row.id)
        await self._session.flush()
        return created
