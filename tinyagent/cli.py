import asyncio
import os
import shutil
import sys
import traceback
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

import typer
from loguru import logger
from rich.console import Console
from typer.core import TyperGroup

from tinyagent.agent import Agent
from tinyagent.channel_base import BaseChannel
from tinyagent.channel_feishu import FeishuChannel
from tinyagent.channel_terminal import TerminalChannel
from tinyagent.config import (
    Config,
    get_config_path,
    get_logs_dir,
    get_workspace_path,
    load_config,
    save_config,
    set_config_path,
)


def write_crash(workspace: Path, exc_type, exc_val, exc_tb) -> None:
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        return
    crash_info = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    crash_file = workspace / f"crash_{ts}.log"
    crash_file.write_text(f"Crash at {datetime.now().isoformat()}\n\n{crash_info}")
    sys.exit(1)


def _make_crash_handler(workspace: Path):
    def crash_handler(exc_type, exc_val, exc_tb):
        write_crash(workspace, exc_type, exc_val, exc_tb)
    return crash_handler


def _setup_logging(stderr=False):
    log_dir = get_logs_dir()
    logger.remove()
    logger.add(log_dir / "tinyagent.log", rotation="1 day", retention="7 days")
    logger.add(lambda msg: print(msg, end=""), level="ERROR")
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
    if config_path:
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            logger.error("Config file not found: {}", path)
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
    if workspace:
        config.agent.workspace = workspace
        ws_path = Path(workspace).expanduser()
    else:
        ws_path = get_workspace_path()
    if not ws_path.exists():
        ws_path.mkdir(parents=True, exist_ok=True)
        logger.info("Created workspace at {}", ws_path)
        templates = files("tinyagent") / "templates"
        if templates.exists():
            shutil.copytree(templates, ws_path, dirs_exist_ok=True)
    else:
        logger.info("Workspace already exists at {}", ws_path)
        # Ensure skills directory exists even if workspace was created before
        skills_path = ws_path / "skills"
        if not skills_path.exists():
            templates = files("tinyagent") / "templates" / "skills"
            if templates.exists():
                shutil.copytree(templates, skills_path)
                logger.info("Copied skills to {}", skills_path)
    return ws_path


async def _run_agent_loop(agent, channel, workspace: Path):
    try:
        await agent.start()
        await channel.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        write_crash(Path(workspace), type(e), e, e.__traceback__)
    finally:
        await channel.stop()
        await agent.stop()


def _run_agent(
    channel: str,
    workspace: str | None,
    config: str | None,
    logs: bool,
    content: str | None = None,
    chat_id: str = "default",
    enable_cron: bool = True,
    guard: bool = False,
    code_path: str | None = None,
):
    if logs:
        _setup_logging(stderr=True)
    cfg = _load_config(config)
    ws_path = _init_workspace(cfg, workspace)
    if guard and not _guard_running():
        import subprocess
        cp = code_path if code_path else os.getcwd()
        cmd = [sys.executable, "-m", "tinyagent.tinyagent_guard", str(ws_path), cp]
        subprocess.Popen(cmd)
    sys.excepthook = _make_crash_handler(ws_path)
    cfg.agent.workspace = str(ws_path)
    agent = Agent(cfg, ws_path, enable_cron=enable_cron)
    if channel == "terminal":
        ch = TerminalChannel(SimpleNamespace(allow_from=["*"]), agent.bus)
    elif channel == "feishu":
        ch = FeishuChannel(cfg.channel.feishu, agent.bus, cfg.channel)
    elif channel == "dummy":
        ch = BaseChannel(SimpleNamespace(allow_from=["*"]), agent.bus, content, chat_id)
    else:
        raise ValueError(f"Unknown channel: {channel}")
    asyncio.run(_run_agent_loop(agent, ch, ws_path))


def _guard_running() -> bool:
    import os
    import subprocess
    my_pid = os.getpid()
    r = subprocess.run(["pgrep", "-f", "tinyagent_guard"], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    for pid_str in r.stdout.strip().split("\n"):
        if pid_str and int(pid_str) != my_pid:
            return True
    return False


@app.command("gateway", help="Start gateway server.")
def gateway(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    chat_id: str = typer.Option("gateway", "--chat-id", help="Chat session ID"),
    logs: bool = typer.Option(False, "--logs", help="Show logs in terminal"),
    guard: bool = typer.Option(False, "--guard", help="Enable guard mode (auto-restart on crash)"),
    code_path: str | None = typer.Option(None, "--code-path", help="Code path for git rollback (guard mode only)"),
):
    _run_agent(
        channel="feishu",
        workspace=workspace,
        config=config,
        logs=logs,
        chat_id=chat_id,
        guard=guard,
        code_path=code_path,
    )


@app.command("chat", help="Interactive chat mode.")
def chat(
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
        content=None,
        chat_id=chat_id,
        enable_cron=True,
    )


@app.command("message", help="Send a single message.")
def message(
    content: str = typer.Argument(..., help="Message to send"),
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
        content=content,
        chat_id=chat_id,
        enable_cron=False,
    )


if __name__ == "__main__":
    app()
