import asyncio
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.markdown import Markdown

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

        @self._bindings.add(Keys.ControlC)
        def _(event):
            event.app.exit(exception=KeyboardInterrupt)

    async def start(self) -> None:
        self._running = True
        self.console.print("[dim]Terminal channel started. Press Ctrl+C to exit.[/dim]")
        self.console.print()

        while self._running and not self._stop_requested:
            try:
                user_input = await self._session.prompt_async(
                    "> ",
                    key_bindings=self._bindings,
                )
                user_input = user_input.strip()
                if not user_input:
                    continue

                if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                    self._stop_requested = True
                    break

                await self._handle_message(
                    sender_id="user",
                    chat_id="terminal",
                    content=user_input,
                )

            except KeyboardInterrupt:
                self._stop_requested = True
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")

    async def stop(self) -> None:
        self._running = False
        self._stop_requested = True

    async def send(self, msg: OutboundMessage) -> None:
        if msg.metadata.get("_progress"):
            return

        content = msg.content
        if content:
            self.console.print(Markdown(content))
            self.console.print()
