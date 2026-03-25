import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings


class Base(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ChannelConfig(Base):
    model_config = ConfigDict(extra="allow")

    send_progress: bool = True
    send_tool_hints: bool = False


class AgentConfig(Base):
    workspace: str = "~/.tinyagent/workspace"
    model: str = "anthropic/claude-opus-4-5"
    provider: str = "auto"
    max_tokens: int = 8192
    context_window_tokens: int = 65_536
    temperature: float = 0.1
    max_tool_iterations: int = 40
    reasoning_effort: str | None = None


class ProviderSettings(Base):
    api_key: str = ""
    api_base: str | None = None


class ProviderConfig(Base):
    anthropic: ProviderSettings = Field(default_factory=ProviderSettings)
    openai: ProviderSettings = Field(default_factory=ProviderSettings)
    moonshot: ProviderSettings = Field(default_factory=ProviderSettings)
    volcengine_coding_plan: ProviderSettings = Field(default_factory=ProviderSettings)


class GatewayConfig(Base):
    host: str = "0.0.0.0"
    port: int = 18790


class WebSearchConfig(Base):
    provider: str = "brave"
    api_key: str = ""
    base_url: str = ""
    max_results: int = 5


class WebToolsConfig(Base):
    proxy: str | None = None
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
    timeout: int = 60
    path_append: str = ""


class MCPServerConfig(Base):
    type: Literal["stdio", "sse", "streamableHttp"] | None = None
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    tool_timeout: int = 30
    enabled_tools: list[str] = Field(default_factory=lambda: ["*"])


class ToolsConfig(Base):
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class Config(BaseSettings):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    channel: ChannelConfig = Field(default_factory=ChannelConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        return Path(self.agent.workspace).expanduser()

    model_config = ConfigDict(env_prefix="NANOBOT_", env_nested_delimiter="__")


_current_config_path: Path | None = None


def set_config_path(path: Path) -> None:
    global _current_config_path
    _current_config_path = path


def get_config_path() -> Path:
    if _current_config_path:
        return _current_config_path
    return Path.home() / ".tinyagent" / "config.json"


def load_config(config_path: Path) -> Config:
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    return Config.model_validate(data)


def save_config(config: Config, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(by_alias=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_runtime_subdir(name: str) -> Path:
    path = get_config_path().parent
    path.mkdir(parents=True, exist_ok=True)
    path = path / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_media_dir(channel: str | None = None) -> Path:
    base = get_runtime_subdir("media")
    if channel:
        path = base / channel
        path.mkdir(parents=True, exist_ok=True)
        return path
    return base


def get_cron_dir() -> Path:
    return get_runtime_subdir("cron")


def get_logs_dir() -> Path:
    return get_runtime_subdir("logs")


def get_workspace_path(workspace: str | None = None) -> Path:
    path = Path(workspace).expanduser() if workspace else Path.home() / ".tinyagent" / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path

