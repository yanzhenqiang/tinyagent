import asyncio
import os
from pathlib import Path

from loguru import logger

from tinyagent.bus import InboundMessage, MessageBus
from tinyagent.config import Config, get_cron_dir
from tinyagent.cron_service import CronService
from tinyagent.loop import AgentLoop
from tinyagent.provider import LLMProvider
from tinyagent.session import SessionManager


HEARTBEAT = "HEARTBEAT"
GUARD_PROC = "tinyagent_guard"


async def _heartbeat_task(workspace: str):
    while True:
        heartbeat_file = os.path.join(workspace, HEARTBEAT)
        with open(heartbeat_file, "a"):
            os.utime(heartbeat_file, None)
        await asyncio.sleep(5)


class Agent:
    def __init__(
        self,
        config: Config,
        workspace: Path | None = None,
        enable_cron: bool = True,
    ):
        self.config = config
        self.workspace = workspace or config.workspace_path
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.bus = MessageBus()

        # Initialize provider
        model = config.agent.model
        provider_name = config.agent.provider
        p = getattr(config.provider, provider_name, None)

        self.provider = LLMProvider(
            api_key=p.api_key if p else "",
            api_base=p.api_base if p else None,
            default_model=model,
            provider_name=provider_name,
            temperature=config.agent.temperature,
            max_tokens=config.agent.max_tokens,
            reasoning_effort=config.agent.reasoning_effort,
        )

        self.session_manager = SessionManager(self.workspace)

        # Initialize cron service if enabled
        self.cron: CronService | None = None
        if enable_cron:
            cron_store_path = get_cron_dir() / "jobs.json"
            self.cron = CronService(cron_store_path, bus=self.bus)

        self.loop = AgentLoop(
            bus=self.bus,
            provider=self.provider,
            workspace=self.workspace,
            model=config.agent.model,
            max_iterations=config.agent.max_tool_iterations,
            context_window_tokens=config.agent.context_window_tokens,
            web_search_config=config.tools.web.search,
            web_proxy=config.tools.web.proxy or None,
            exec_config=config.tools.exec,
            cron_service=self.cron,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            session_manager=self.session_manager,
            mcp_servers=config.tools.mcp_servers,
            channel_config=config.channel,
        )

        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True

        self._tasks.append(asyncio.create_task(_heartbeat_task(str(self.workspace))))

        if self.cron:
            await self.cron.start()

        self._tasks.append(asyncio.create_task(self.loop.run()))
        logger.info("Agent started")

    async def stop(self) -> None:
        """Stop the agent loop."""
        if not self._running:
            return
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        if self.cron:
            self.cron.stop()

        self.loop.stop()
        await self.loop.close_mcp()
        logger.info("Agent stopped")

    async def process_message(
        self,
        content: str,
        channel: str = "cli",
        chat_id: str = "default",
        sender_id: str = "user",
        session_key: str | None = None,
    ) -> str | None:
        """Process a single message and return the response directly."""
        msg = InboundMessage(
            channel=channel,
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            session_key_override=session_key or f"{channel}:{chat_id}",
        )

        # Use the loop's _process_message directly
        response = await self.loop._process_message(msg)
        return response.content if response else None
