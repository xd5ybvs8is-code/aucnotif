from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, telegram_id: int, timezone: str, language: str) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is not None:
            if user.timezone != timezone:
                user.timezone = timezone
                await self._session.flush()
            return user
        user = User(telegram_id=telegram_id, timezone=timezone, language=language)
        self._session.add(user)
        await self._session.flush()
        return user
