import asyncio
import os
from pathlib import Path

from loguru import logger

from tinyagent.bus import MessageBus
from tinyagent.config import Config, get_cron_dir
from tinyagent.cron_service import CronService
from tinyagent.loop import AgentLoop
from tinyagent.provider import LLMProvider
from tinyagent.session import SessionManager


async def _heartbeat_task(workspace: str):
    while True:
        heartbeat_file = os.path.join(workspace, "HEARTBEAT")
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
        self.workspace = workspace
        self.bus = MessageBus()
        model = config.agent.model
        provider_name = config.agent.provider
        p = getattr(config.provider, provider_name, None)

        self.provider = LLMProvider(
            api_key=p.api_key if p else "",
            api_base=p.api_base if p else None,
            default_model=model,
            temperature=config.agent.temperature,
            max_tokens=config.agent.max_tokens,
            reasoning_effort=config.agent.reasoning_effort,
        )

        self.session_manager = SessionManager(self.workspace)

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
            exec_config=config.tools.exec,
            cron_service=self.cron,
            restrict_to_workspace=config.tools.restrict_to_workspace,
            session_manager=self.session_manager,
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
        loop_task = asyncio.create_task(self.loop.run())
        loop_task.add_done_callback(self._on_loop_done)
        self._tasks.append(loop_task)
        logger.info("Agent started")

    def _on_loop_done(self, task):
        if task.exception():
            logger.error("Agent loop crashed: {}", task.exception())
            import sys
            sys.exit(1)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self.cron:
            self.cron.stop()
        self.loop.stop()
        logger.info("Agent stopped")
