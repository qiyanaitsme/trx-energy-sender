import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from sqlalchemy import select

from database import async_session, User
from config import config


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[int, list[float]] = {}

    def is_allowed(self, user_id: int) -> bool:
        now = time.time()
        if user_id not in self._requests:
            self._requests[user_id] = []

        self._requests[user_id] = [
            t for t in self._requests[user_id]
            if now - t < self.window_seconds
        ]

        if len(self._requests[user_id]) >= self.max_requests:
            return False

        self._requests[user_id].append(now)
        return True


rate_limiter = RateLimiter(
    max_requests=config.RATE_LIMIT_REQUESTS,
    window_seconds=config.RATE_LIMIT_WINDOW,
)


class BlockCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None

        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not user:
            return await handler(event, data)

        user_id = user.id
        username = user.username

        if user_id not in config.ADMIN_IDS:
            if not rate_limiter.is_allowed(user_id):
                if isinstance(event, Message):
                    await event.answer("⏳ Слишком много запросов. Подожди минуту.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⏳ Слишком много запросов", show_alert=True)
                return None

        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            db_user = result.scalar_one_or_none()

            if db_user is None:
                db_user = User(telegram_id=user_id, username=username)
                session.add(db_user)
                await session.commit()
            elif db_user.username != username:
                db_user.username = username
                await session.commit()

            if db_user.is_blocked:
                if isinstance(event, Message):
                    await event.answer("🚫 <b>ВЫ ЗАБЛОКИРОВАНЫ В БОТЕ</b>", parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer("🚫 ВЫ ЗАБЛОКИРОВАНЫ В БОТЕ", show_alert=True)
                return None

        return await handler(event, data)
