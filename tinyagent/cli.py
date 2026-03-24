import asyncio
from pathlib import Path

import typer
from rich.console import Console
from typer.core import TyperGroup

from tinyagent import __logo__
from tinyagent.config import Config, get_workspace_path


def _setup_logging(stderr=False):
    from loguru import logger
    from tinyagent.config import get_logs_dir
    log_dir = get_logs_dir()
    logger.remove()
    logger.add(log_dir / "tinyagent.log", rotation="1 day", retention="7 days")
    if stderr:
        logger.add(lambda msg: print(msg, end=""), filter=lambda rec: rec["level"].name != "DEBUG")


class NoOptionsGroup(TyperGroup):
    def format_help(self, ctx, formatter):
        self.format_usage(ctx, formatter)
        self.format_commands(ctx, formatter)

_setup_logging()

app = typer.Typer(
    name="tinyagent",
    no_args_is_help=True,
    add_completion=False,
    cls=NoOptionsGroup,
)

console = Console()


def _load_config(config_path: str | None) -> Config:
    from loguru import logger
    from tinyagent.config import (
        get_config_path,
        load_config,
        save_config,
        set_config_path,
    )

    if config_path:
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            console.print(f"[red]Error: Config file not found: {path}[/red]")
            raise typer.Exit(1)
        set_config_path(path)
        logger.info("Using config: {}", path)
    else:
        path = get_config_path()

    if not path.exists():
        save_config(Config(), path)
        logger.info("Created config at {}", path)

    return load_config(path)


def _init_workspace(config: Config, workspace: str | None) -> Path:
    from loguru import logger
    if workspace:
        config.agent.workspace = workspace
        ws_path = Path(workspace).expanduser()
    else:
        ws_path = get_workspace_path()

    if not ws_path.exists():
        ws_path.mkdir(parents=True, exist_ok=True)
        logger.info("Created workspace at {}", ws_path)
        import shutil
        from importlib.resources import files
        templates = files("tinyagent") / "templates"
        if templates.exists():
            shutil.copytree(templates, ws_path, dirs_exist_ok=True)
    else:
        logger.info("Workspace already exists at {}", ws_path)

    return ws_path


@app.command("gateway", help="Start gateway server.")
def gateway(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    logs: bool = typer.Option(False, "--logs", help="Show logs in terminal"),
):
    if logs:
        _setup_logging(stderr=True)
    from tinyagent.agent import Agent
    from tinyagent.channel_feishu import FeishuChannel

    cfg = _load_config(config)
    ws_path = _init_workspace(cfg, workspace)
    cfg.agent.workspace = str(ws_path)
    async def run():
        agent = Agent(cfg, ws_path)
        feishu_ch = FeishuChannel(cfg.channel.feishu, agent.bus, cfg.channel)

        try:
            await agent.start()
            await feishu_ch.start()
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        except Exception:
            import traceback
            console.print("\n[red]Error: Gateway crashed unexpectedly[/red]")
            console.print(traceback.format_exc())
        finally:
            await feishu_ch.stop()
            await agent.stop()

    asyncio.run(run())


@app.command("chat", help="Interactive chat mode.")
def chat(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    logs: bool = typer.Option(False, "--logs", help="Show logs in terminal"),
):
    if logs:
        _setup_logging(stderr=True)
    from tinyagent.agent import Agent
    from tinyagent.channel_terminal import TerminalChannel

    cfg = _load_config(config)
    ws_path = _init_workspace(cfg, workspace)
    cfg.agent.workspace = str(ws_path)
    class TerminalConfig:
        allow_from = ["*"]
    async def run():
        agent = Agent(cfg, ws_path)
        terminal = TerminalChannel(TerminalConfig(), agent.bus)

        try:
            await agent.start()
            await terminal.start()
        except KeyboardInterrupt:
            pass
        finally:
            await terminal.stop()
            await agent.stop()

    asyncio.run(run())


@app.command("message", help="Send a single message.")
def message(
    content: str = typer.Argument(..., help="Message to send"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    chat_id: str = typer.Option("cli", "--chat-id", help="Chat session ID"),
    logs: bool = typer.Option(False, "--logs", help="Show logs in terminal"),
):
    """Send a single message and get a response."""
    if logs:
        _setup_logging(stderr=True)
    from tinyagent.agent import Agent
    from tinyagent.channel_direct import DirectChannel

    cfg = _load_config(config)
    ws_path = _init_workspace(cfg, workspace)

    async def run():
        agent = Agent(cfg, ws_path, enable_cron=False)
        direct = DirectChannel(None, agent.bus)

        try:
            await agent.start()
            channel_task = asyncio.create_task(direct.start())
            response = await direct.send_message_and_wait(
                content=content,
                sender_id="user",
                chat_id=chat_id,
            )
            if response:
                console.print(response)
            await direct.stop()
            channel_task.cancel()
            try:
                await channel_task
            except asyncio.CancelledError:
                pass
        finally:
            await agent.stop()

    asyncio.run(run())


@app.command("status", help="Show status.")
def status():
    from tinyagent.config import get_config_path, load_config

    config_path = get_config_path()
    cfg = load_config(config_path)
    workspace = cfg.workspace_path
    console.print(f"{__logo__} tinyagent Status\n")
    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")

    if config_path.exists():
        from tinyagent.provider import PROVIDERS
        console.print(f"Model: {cfg.agent.model}")
        for spec in PROVIDERS:
            p = getattr(cfg.provider, spec.name, None)
            if p is None:
                continue
            has_key = bool(p.api_key)
            console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}"  )

        # Show channel status
        console.print()
        feishu_cfg = getattr(cfg.channel, "feishu", None)
        status = "[green]✓[/green]" if feishu_cfg else "[dim]not set[/dim]"
        console.print(f"Feishu: {status}")


if __name__ == "__main__":
    app()
