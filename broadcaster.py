import asyncio
import logging
from datetime import datetime

from telegram import Bot
from telegram.error import RetryAfter, TelegramError

logger = logging.getLogger(__name__)


class ControlledBroadcaster:
    def __init__(self, bot: Bot, send_delay: float = 0.5):
        self.bot = bot
        self.send_delay = send_delay

    async def send_with_retry(self, chat_id: int, text: str):
        try:
            await self.bot.send_message(chat_id=chat_id, text=text)
            return True, None
        except RetryAfter as exc:
            logger.warning("Rate limited by Telegram for chat_id=%s; waiting %s seconds", chat_id, exc.retry_after)
            await asyncio.sleep(float(exc.retry_after))
            try:
                await self.bot.send_message(chat_id=chat_id, text=text)
                return True, None
            except TelegramError as error:
                return False, str(error)
        except TelegramError as exc:
            return False, str(exc)

    async def send_batch(self, recipients: list[tuple[str, int]], text: str) -> list[dict]:
        results: list[dict] = []
        for email, chat_id in recipients:
            ok, error = await self.send_with_retry(chat_id, text)
            status = "sent" if ok else "failed"
            results.append(
                {
                    "email": email,
                    "chat_id": chat_id,
                    "status": status,
                    "error": error,
                    "sent_at": datetime.utcnow().isoformat(timespec="seconds") if ok else None,
                }
            )
            if self.send_delay > 0:
                await asyncio.sleep(self.send_delay)
        return results
