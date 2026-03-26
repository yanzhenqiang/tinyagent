import asyncio
import json
import logging
import os
import re
import sys
import traceback
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from loguru import logger

from tinyagent.bus import InboundMessage, MessageBus, OutboundMessage
from tinyagent.config import ChannelConfig, ExecToolConfig, WebSearchConfig
from tinyagent.context import ContextBuilder
from tinyagent.cron_service import CronService
from tinyagent.memory import MemoryConsolidator
from tinyagent.provider import PROVIDERS, LLMProvider
from tinyagent.session import Session, SessionManager
from tinyagent.tools.cron import CronTool
from tinyagent.tools.mcp import connect_mcp_servers
from tinyagent.tools.message import MessageTool
from tinyagent.tools.registry import ToolRegistry
from tinyagent.tools.shell import ExecTool
from tinyagent.tools.web import WebFetchTool, WebSearchTool


class AgentLoop:
    _TOOL_RESULT_MAX_CHARS = 16_000

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        context_window_tokens: int = 65_536,
        web_search_config: WebSearchConfig | None = None,
        web_proxy: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channel_config: ChannelConfig | None = None,
    ):

        self.bus = bus
        self.channel_config = channel_config
        self.provider = provider
        self.workspace = workspace
        self.model = model
        self.max_iterations = max_iterations
        self.context_window_tokens = context_window_tokens
        self.web_search_config = web_search_config or WebSearchConfig()
        self.web_proxy = web_proxy
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._active_tasks: dict[str, list[asyncio.Task]] = {}
        self._background_tasks: list[asyncio.Task] = []
        self._processing_lock = asyncio.Lock()
        self.memory_consolidator = MemoryConsolidator(
            workspace=workspace,
            provider=provider,
            model=self.model,
            sessions=self.sessions,
            context_window_tokens=context_window_tokens,
            build_messages=self.context.build_messages,
            get_tool_definitions=self.tools.get_definitions,
        )
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
            path_append=self.exec_config.path_append,
        ))
        self.tools.register(WebSearchTool(config=self.web_search_config, proxy=self.web_proxy))
        self.tools.register(WebFetchTool(proxy=self.web_proxy))
        self.tools.register(MessageTool(send_callback=self.bus.outbound.put))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    async def _cmd_new(self, msg: InboundMessage) -> OutboundMessage:
        session = self.sessions.get_or_create(msg.session_key)
        snapshot = session.messages[session.last_consolidated:]
        session.clear()
        self.sessions.save(session)
        self.sessions.invalidate(session.key)
        if snapshot:
            self._schedule_background(self.memory_consolidator.archive_messages(snapshot))
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="New session started.")

    async def _cmd_debug_on(self, msg: InboundMessage) -> OutboundMessage:
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="httpx debug logging enabled.")

    async def _cmd_debug_off(self, msg: InboundMessage) -> OutboundMessage:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="httpx debug logging disabled.")

    async def _cmd_help(self, msg: InboundMessage) -> OutboundMessage:
        lines = [
            "/new — Start a new conversation",
            "/stop — Stop the current task",
            "/restart — Restart the bot",
            "/debug_on — Enable httpx debug logging",
            "/debug_off — Disable httpx debug logging",
            "/help — Show available commands",
        ]
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="\n".join(lines))

    async def _cmd_stop(self, msg: InboundMessage) -> OutboundMessage:
        tasks = self._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        content = f"Stopped {cancelled} task(s)." if cancelled else "No active task to stop."
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content)

    async def _cmd_restart(self, msg: InboundMessage) -> OutboundMessage:
        async def _do_restart():
            await asyncio.sleep(1)
            os.environ["TINYAGENT_RESTART"] = f"{msg.channel}:{msg.chat_id}"
            os.execv(sys.executable, [sys.executable, "-m", "tinyagent"] + sys.argv[1:])
        asyncio.create_task(_do_restart())
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="Restarting...")

    async def _cmd_status(self, msg: InboundMessage) -> OutboundMessage:
        lines = ["🐍 tinyagent Status\n", f"Model: {self.model}"]
        for spec in PROVIDERS:
            p = getattr(self.provider.config if hasattr(self.provider, 'config') else self.provider, spec.name, None)
            if p is None:
                continue
            has_key = bool(p.api_key if hasattr(p, 'api_key') else False)
            lines.append(f"{spec.label}: {'✓' if has_key else 'not set'}")
        return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content="\n".join(lines))

    _COMMAND_HANDLERS = {
        "/new": _cmd_new,
        "/stop": _cmd_stop,
        "/restart": _cmd_restart,
        "/status": _cmd_status,
        "/debug_on": _cmd_debug_on,
        "/debug_off": _cmd_debug_off,
        "/help": _cmd_help,
    }

    async def _connect_mcp(self) -> None:
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1
            response = await self.provider.chat_with_retry(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
            )
            if response.has_tool_calls:
                if on_progress:
                    thought = self._strip_think(response.content)
                    if thought:
                        await on_progress(thought)
                    tool_hint = self._tool_hint(response.tool_calls)
                    tool_hint = self._strip_think(tool_hint)
                    await on_progress(tool_hint, tool_hint=True)

                tool_use_blocks = [tc.to_anthropic_format() for tc in response.tool_calls]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_use_blocks,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, result
                    )
            else:
                clean = self._strip_think(response.content)
                if response.finish_reason == "error":
                    logger.error("LLM returned error: {}", (clean or "")[:200])
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.inbound.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning("Error consuming inbound message: {}, continuing...", e)
                continue

            cmd = msg.content.strip().lower()
            if handler := self._COMMAND_HANDLERS.get(cmd):
                response = await handler(self, msg)
                if response:
                    await self.bus.outbound.put(response)
            else:
                task = asyncio.create_task(self._dispatch(msg))
                self._active_tasks.setdefault(msg.session_key, []).append(task)
                task.add_done_callback(lambda t, k=msg.session_key: self._active_tasks.get(k, []) and self._active_tasks[k].remove(t) if t in self._active_tasks.get(k, []) else None)

    async def _dispatch(self, msg: InboundMessage) -> None:
        async with self._processing_lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.outbound.put(response)
                elif msg.channel == "cli":
                    await self.bus.outbound.put(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception as e:
                crash_info = traceback.format_exc()
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    logger.info("Expected exit: {}", e)
                    raise

                logger.error("Crash: {}", crash_info)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                crash_file = self.workspace / f"crash_{ts}.log"
                crash_file.write_text(f"Crash at {datetime.now().isoformat()}\n\n{crash_info}")
                raise

    async def close_mcp(self) -> None:
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def _schedule_background(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        task.add_done_callback(self._background_tasks.remove)

    def stop(self) -> None:
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_system_message(self, msg: InboundMessage, on_progress) -> OutboundMessage:
        channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id))
        logger.info("Processing system message from {}", msg.sender_id)
        key = f"{channel}:{chat_id}"
        session = self.sessions.get_or_create(key)
        await self.memory_consolidator.maybe_consolidate_by_tokens(session)
        self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
        history = session.get_history(max_messages=0)
        messages = self.context.build_messages(
            history=history, current_message=msg.content, channel=channel, chat_id=chat_id
        )
        final_content, _, all_msgs = await self._run_agent_loop(messages, on_progress=on_progress)
        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)
        self._schedule_background(self.memory_consolidator.maybe_consolidate_by_tokens(session))
        return OutboundMessage(channel=channel, chat_id=chat_id, content=final_content or "Background task completed.")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        if msg.channel == "system":
            return await self._process_system_message(msg, on_progress)

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        cmd = msg.content.strip().lower()
        if handler := self._COMMAND_HANDLERS.get(cmd):
            return handler(self, msg, session)
        await self.memory_consolidator.maybe_consolidate_by_tokens(session)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history = session.get_history(max_messages=0)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.outbound.put(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages, on_progress=on_progress or _bus_progress,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)
        self._schedule_background(self.memory_consolidator.maybe_consolidate_by_tokens(session))

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        for m in messages[skip:]:
            entry = self._clean_message(dict(m))
            if entry:
                entry.setdefault("timestamp", datetime.now().isoformat())
                session.messages.append(entry)
        session.updated_at = datetime.now()

    def _clean_message(self, msg: dict) -> dict | None:
        role, content = msg.get("role"), msg.get("content")
        if role == "assistant" and not content and not msg.get("tool_calls"):
            return None
        if role == "tool" and isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
            msg["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
        elif role == "user":
            msg["content"] = self._clean_user_content(content)
            if msg["content"] is None:
                return None
        return msg

    def _clean_user_content(self, content: str | list) -> str | list | None:
        if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
            parts = content.split("\n\n", 1)
            return parts[1] if len(parts) > 1 and parts[1].strip() else None
        if not isinstance(content, list):
            return content
        filtered = []
        for c in content:
            if c.get("type") == "text" and isinstance(c.get("text"), str) and c["text"].startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                continue
            if c.get("type") == "image_url" and c.get("image_url", {}).get("url", "").startswith("data:image/"):
                filtered.append({"type": "text", "text": "[image]"})
            else:
                filtered.append(c)
        return filtered if filtered else None
