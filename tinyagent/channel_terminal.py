import asyncio
import itertools
import sys
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console

from tinyagent import __logo__
from tinyagent.bus import MessageBus, OutboundMessage
from tinyagent.channel_base import BaseChannel


class TerminalChannel(BaseChannel):
    name = "terminal"
    display_name = "Terminal"

    def __init__(self, config: Any, bus: MessageBus):
        super().__init__(config, bus)
        self.console = Console()
        self._session = PromptSession()
        self._bindings = KeyBindings()
        self._stop_requested = False
        self._response_event = asyncio.Event()

        @self._bindings.add(Keys.ControlC)
        def _(event):
            event.app.exit(exception=KeyboardInterrupt)

    async def start(self) -> None:
        self._running = True
        self._current_response = None
        outbound_task = asyncio.create_task(self._dispatch_outbound())

        while self._running and not self._stop_requested:
            try:
                user_input = await self._session.prompt_async(
                    "You> ",
                    key_bindings=self._bindings,
                )
                user_input = user_input.strip()
                if not user_input:
                    continue

                if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                    self._stop_requested = True
                    break

                self._response_event.clear()
                self._current_response = None

                await self._handle_message(
                    sender_id="user",
                    chat_id="terminal",
                    content=user_input,
                )

                await self._show_spinner_until_response()

            except KeyboardInterrupt:
                self._stop_requested = True
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")

        outbound_task.cancel()
        try:
            await outbound_task
        except asyncio.CancelledError:
            pass

    async def _show_spinner_until_response(self) -> None:
        spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        while not self._response_event.is_set():
            sys.stdout.write(f"\r{next(spinner)} Thinking...")
            sys.stdout.flush()
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                continue
        sys.stdout.write("\r" + " " * 20 + "\r")
        sys.stdout.flush()
        if self._current_response:
            print(f"{__logo__}> {self._current_response}")
            print()

    async def stop(self) -> None:
        self._running = False
        self._stop_requested = True

    async def send(self, msg: OutboundMessage) -> None:
        if msg.metadata.get("_progress"):
            return

        content = msg.content
        if content:
            self._current_response = content
            self._response_event.set()
