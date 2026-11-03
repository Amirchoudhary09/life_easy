"""Telegram Bot API (webhook mode)."""

from __future__ import annotations

import hmac
from typing import Any

import httpx

from app.channels.base import Button, ChannelAdapter, InboundMessage, chunk_text
from app.config import get_settings
from app.core.errors import ProviderError, ProviderNotConfigured


class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    def configured(self) -> bool:
        return bool(get_settings().telegram_bot_token)

    def valid_secret(self, header_value: str | None) -> bool:
        secret = get_settings().telegram_webhook_secret
        if not secret:
            return False
        return hmac.compare_digest(header_value or "", secret)

    def parse(self, payload: dict[str, Any]) -> list[InboundMessage]:
        update_id = str(payload.get("update_id", ""))
        if msg := payload.get("message"):
            chat = msg.get("chat") or {}
            sender = msg.get("from") or {}
            name = " ".join(x for x in (sender.get("first_name"), sender.get("last_name")) if x) or sender.get("username")
            text = str(msg.get("text") or msg.get("caption") or "")
            if text.startswith("/start"):
                text = text.replace("/start", "", 1).strip() or "hello"
            return [
                InboundMessage(
                    provider=self.name,
                    external_id=str(chat.get("id", "")),
                    text=text,
                    event_id=f"u{update_id}",
                    display_name=name,
                )
            ]
        if cb := payload.get("callback_query"):
            msg = cb.get("message") or {}
            chat = msg.get("chat") or {}
            sender = cb.get("from") or {}
            name = " ".join(x for x in (sender.get("first_name"), sender.get("last_name")) if x)
            return [
                InboundMessage(
                    provider=self.name,
                    external_id=str(chat.get("id", "")),
                    text="",
                    event_id=f"cb{cb.get('id', update_id)}",
                    display_name=name,
                    button_id=str(cb.get("data", "")),
                    reply_to={"callback_query_id": cb.get("id"), "message_id": msg.get("message_id")},
                )
            ]
        return []

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{get_settings().telegram_bot_token}/{method}"

    async def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            raise ProviderNotConfigured("Telegram bot token is not configured")
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(self._url(method), json=payload)
        if resp.is_error:
            raise ProviderError(f"Telegram {method} failed with HTTP {resp.status_code}")
        return resp.json()

    async def send_text(self, external_id: str, text: str) -> None:
        for chunk in chunk_text(text):
            await self._call("sendMessage", {"chat_id": external_id, "text": chunk, "disable_web_page_preview": True})

    async def send_buttons(self, external_id: str, text: str, buttons: list[Button]) -> None:
        chunks = chunk_text(text)
        for chunk in chunks[:-1]:
            await self._call("sendMessage", {"chat_id": external_id, "text": chunk, "disable_web_page_preview": True})
        keyboard = [[{"text": b.label[:40], "callback_data": b.id[:64]}] for b in buttons[:8]]
        await self._call(
            "sendMessage",
            {
                "chat_id": external_id,
                "text": chunks[-1] if chunks else "Choose an option",
                "reply_markup": {"inline_keyboard": keyboard},
                "disable_web_page_preview": True,
            },
        )

    async def acknowledge(self, message: InboundMessage) -> None:
        cb = message.reply_to.get("callback_query_id")
        if cb:
            try:
                await self._call("answerCallbackQuery", {"callback_query_id": cb})
            except ProviderError:
                pass

    async def set_webhook(self, url: str) -> dict[str, Any]:
        return await self._call(
            "setWebhook",
            {
                "url": url,
                "secret_token": get_settings().telegram_webhook_secret,
                "allowed_updates": ["message", "callback_query"],
            },
        )
