import asyncio
import importlib
from abc import ABC
from typing import Any

from loguru import logger

from tinyagent.bus import InboundMessage, MessageBus

CHANNEL_REGISTRY = {
    "feishu": "tinyagent.channel_feishu:FeishuChannel",
    "terminal": "tinyagent.channel_terminal:TerminalChannel",
    "dummy": "tinyagent.channel_base:BaseChannel",
}


def create_channel(
    channel_type: str,
    config: Any,
    bus: MessageBus,
    content: str | None = None,
    chat_id: str = "cli",
    global_config: Any = None,
) -> "BaseChannel":
    if channel_type not in CHANNEL_REGISTRY:
        raise ValueError(f"Unknown channel type: {channel_type}. "
                        f"Supported types: {list(CHANNEL_REGISTRY.keys())}")

    module_path, class_name = CHANNEL_REGISTRY[channel_type].rsplit(":", 1)
    module = importlib.import_module(module_path)
    channel_class = getattr(module, class_name)

    if channel_type == "dummy":
        return channel_class(config, bus, content, chat_id)
    elif channel_type == "feishu":
        return channel_class(config, bus, global_config)
    return channel_class(config, bus)


class BaseChannel(ABC):
    name: str = "base"
    display_name: str = "Base"
    transcription_api_key: str = ""
    _dispatch_timeout: float = 1.0

    def __init__(self, config: Any, bus: MessageBus, content: str | None = None, chat_id: str = "cli"):
        self.config = config
        self.bus = bus
        self._running = False
        self._content = content
        self._chat_id = chat_id
        self._response = None
        self._event = asyncio.Event()

    async def start(self) -> None:
        self._running = True
        if self._content:
            await self._handle_message(sender_id="user", chat_id=self._chat_id, content=self._content)
            try:
                await asyncio.wait_for(self._event.wait(), timeout=300)
            except asyncio.TimeoutError:
                pass
            self._running = False
        await self._dispatch_outbound()

    async def stop(self) -> None:
        self._running = False
        self._event.set()

    async def send(self, msg):
        if not msg.metadata.get("_progress"):
            print(msg.content)
            self._event.set()

    async def _dispatch_outbound(self) -> None:
        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.outbound.get(), timeout=self._dispatch_timeout)
                await self.send(msg)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def is_allowed(self, sender_id: str) -> bool:
        allow_list = getattr(self.config, "allow_from", [])
        if not allow_list:
            logger.warning("{}: allow_from is empty — all access denied", self.name)
            return False
        if "*" in allow_list:
            return True
        return str(sender_id) in allow_list

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        session_key: str | None = None,
    ) -> None:
        if not self.is_allowed(sender_id):
            logger.warning(
                "Access denied for sender {} on channel {}. "
                "Add them to allowFrom list in config to grant access.",
                sender_id, self.name,
            )
            return

        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media or [],
            metadata=metadata or {},
        )
        await self.bus.inbound.put(msg)

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return {"enabled": False}

    @property
    def is_running(self) -> bool:
        return self._running


