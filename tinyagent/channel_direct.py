import asyncio
from typing import Any

from tinyagent.bus import MessageBus, OutboundMessage
from tinyagent.channel_base import BaseChannel


class DirectChannel(BaseChannel):
    """Minimal channel for single-message request/response."""

    name = "direct"
    display_name = "Direct"

    def __init__(self, config: Any, bus: MessageBus):
        from types import SimpleNamespace
        if config is None:
            config = SimpleNamespace(allow_from=["*"])
        super().__init__(config, bus)
        self._response = None
        self._event = asyncio.Event()

    async def start(self) -> None:
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.outbound.get(), timeout=0.5)
                await self.send(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        if msg.metadata.get("_progress"):
            return
        self._response = msg.content
        self._event.set()

    async def send_message_and_wait(
        self,
        content: str,
        sender_id: str = "user",
        chat_id: str = "cli",
    ) -> str | None:
        """Send a single message and wait for response."""
        self._event.clear()
        self._response = None

        await self._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
        )

        try:
            await asyncio.wait_for(self._event.wait(), timeout=300)
        except asyncio.TimeoutError:
            return None

        return self._response
