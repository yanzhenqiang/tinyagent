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


async def _run_agent_loop(agent, channel, error_msg: str | None = None):
    try:
        await agent.start()
        await channel.start()
    except KeyboardInterrupt:
        pass
    except Exception:
        if error_msg:
            import traceback
            console.print(f"\n[red]Error: {error_msg}[/red]")
            console.print(traceback.format_exc())
        raise
    finally:
        await channel.stop()
        await agent.stop()


def _resolve_channel_config(cfg: Config, channel: str):
    from types import SimpleNamespace

    from tinyagent.config import ChannelInstanceConfig
    if channel in cfg.channel.instances:
        instance_cfg = cfg.channel.instances[channel]
        if not isinstance(instance_cfg, ChannelInstanceConfig):
            instance_cfg = ChannelInstanceConfig.model_validate(instance_cfg)
        return instance_cfg.type, instance_cfg.config, cfg.channel
    if channel == "terminal":
        return "terminal", SimpleNamespace(allow_from=["*"]), cfg.channel
    elif channel == "feishu":
        return "feishu", cfg.channel.feishu if hasattr(cfg.channel, "feishu") else {}, cfg.channel
    elif channel == "dummy":
        return "dummy", SimpleNamespace(allow_from=["*"]), cfg.channel
    else:
        raise ValueError(f"Unknown channel: {channel}")


def _run_agent(
    channel: str,
    workspace: str | None,
    config: str | None,
    logs: bool,
    content: str | None = None,
    chat_id: str = "default",
    enable_cron: bool = True,
    error_msg: str | None = None,
):
    if logs:
        _setup_logging(stderr=True)
    from tinyagent.agent import Agent
    from tinyagent.channel_base import create_channel

    cfg = _load_config(config)
    ws_path = _init_workspace(cfg, workspace)
    cfg.agent.workspace = str(ws_path)

    channel_type, channel_cfg, global_cfg = _resolve_channel_config(cfg, channel)
    agent = Agent(cfg, ws_path, enable_cron=enable_cron)

    ch = create_channel(
        channel_type=channel_type,
        config=channel_cfg,
        bus=agent.bus,
        content=content,
        chat_id=chat_id,
        global_config=global_cfg,
    )

    try:
        asyncio.run(_run_agent_loop(agent, ch, error_msg))
    except KeyboardInterrupt:
        console.print("\nShutting down...")


@app.command("gateway", help="Start gateway server.")
def gateway(
    init_content: str = typer.Argument(..., help="Message to send"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    chat_id: str = typer.Option("gateway", "--chat-id", help="Chat session ID"),
    logs: bool = typer.Option(False, "--logs", help="Show logs in terminal"),
):
    _run_agent(
        channel="feishu",
        workspace=workspace,
        config=config,
        logs=logs,
        content=init_content,
        chat_id=chat_id,
        enable_cron=True,
        error_msg="Gateway crashed unexpectedly",
    )


@app.command("chat", help="Interactive chat mode.")
def chat(
    init_content: str = typer.Argument(..., help="Message to send"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    chat_id: str = typer.Option("chat", "--chat-id", help="Chat session ID"),
    logs: bool = typer.Option(False, "--logs", help="Show logs in terminal"),
):
    _run_agent(
        channel="terminal",
        workspace=workspace,
        config=config,
        logs=logs,
        content=init_content,
        chat_id=chat_id,
        enable_cron=True,
    )


@app.command("message", help="Send a single message.")
def message(
    init_content: str = typer.Argument(..., help="Message to send"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    chat_id: str = typer.Option("message", "--chat-id", help="Chat session ID"),
    logs: bool = typer.Option(False, "--logs", help="Show logs in terminal"),
):
    _run_agent(
        channel="dummy",
        workspace=workspace,
        config=config,
        logs=logs,
        content=init_content,
        chat_id=chat_id,
        enable_cron=False,
    )


if __name__ == "__main__":
    app()
