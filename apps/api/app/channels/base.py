"""Channel adapters: one small class per messaging provider, one pipeline for all of them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_MESSAGE_CHARS = 3900


@dataclass
class InboundMessage:
    provider: str
    external_id: str  # wa_id / telegram chat id
    text: str
    event_id: str  # provider message id, used for de-duplication
    display_name: str | None = None
    button_id: str | None = None  # interactive reply / callback data
    reply_to: dict[str, Any] = field(default_factory=dict)  # provider-specific ids (callback query id, ...)


@dataclass
class Button:
    id: str
    label: str


class ChannelAdapter:
    name = "base"

    def configured(self) -> bool:
        return False

    def parse(self, payload: dict[str, Any]) -> list[InboundMessage]:
        raise NotImplementedError

    async def send_text(self, external_id: str, text: str) -> None:
        raise NotImplementedError

    async def send_buttons(self, external_id: str, text: str, buttons: list[Button]) -> None:
        raise NotImplementedError

    async def acknowledge(self, message: InboundMessage) -> None:  # noqa: B027 - optional hook
        """Called once an inbound message was accepted (answer callback queries, read receipts)."""


def chunk_text(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks
