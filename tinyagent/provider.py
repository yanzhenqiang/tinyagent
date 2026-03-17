import asyncio
import hashlib
import json
import os
import secrets
import string
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic
from loguru import logger


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]
    provider_specific_fields: dict[str, Any] | None = None
    function_provider_specific_fields: dict[str, Any] | None = None

    def to_openai_tool_call(self) -> dict[str, Any]:
        tool_call = {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, ensure_ascii=False),
            },
        }
        if self.provider_specific_fields:
            tool_call["provider_specific_fields"] = self.provider_specific_fields
        if self.function_provider_specific_fields:
            tool_call["function"]["provider_specific_fields"] = self.function_provider_specific_fields
        return tool_call


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None
    thinking_blocks: list[dict] | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


@dataclass(frozen=True)
class GenerationSettings:
    temperature: float = 0.7
    max_tokens: int = 4096
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    env_key: str
    display_name: str = ""
    skip_prefixes: tuple[str, ...] = ()
    env_extras: tuple[tuple[str, str], ...] = ()
    detect_by_key_prefix: str = ""
    default_api_base: str = ""
    strip_model_prefix: bool = False
    model_overrides: tuple[tuple[str, dict[str, Any]], ...] = ()
    supports_prompt_caching: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.name.title()


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="anthropic",
        env_key="ANTHROPIC_API_KEY",
        display_name="Anthropic",
        skip_prefixes=(),
        env_extras=(),
        detect_by_key_prefix="",
        default_api_base="",
        strip_model_prefix=False,
        model_overrides=(),
        supports_prompt_caching=True,
    ),
)


def find_provider_by_name(name: str) -> ProviderSpec | None:
    for spec in PROVIDERS:
        if spec.name == name:
            return spec
    return None


_ALLOWED_MSG_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name", "reasoning_content"})
_ALNUM = string.ascii_letters + string.digits


def _short_tool_id() -> str:
    return "".join(secrets.choice(_ALNUM) for _ in range(9))


class LLMProvider:
    _CHAT_RETRY_DELAYS = (1, 2, 4)
    _TRANSIENT_ERROR_MARKERS = (
        "429",
        "rate limit",
        "500",
        "502",
        "503",
        "504",
        "overloaded",
        "timeout",
        "timed out",
        "connection",
        "server error",
        "temporarily unavailable",
    )
    _IMAGE_UNSUPPORTED_MARKERS = (
        "image_url is only supported",
        "does not support image",
        "images are not supported",
        "image input is not supported",
        "image_url is not supported",
        "unsupported image input",
    )

    _SENTINEL = object()

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "claude-opus-4-5",
        provider_name: str | None = None,
    ):
        self.api_key = api_key
        self.api_base = api_base
        self.default_model = default_model
        self.provider_name = provider_name
        self.generation: GenerationSettings = GenerationSettings()
        self._client = None

        if api_key:
            self._setup_env(api_key, api_base, default_model)

    def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
        spec = find_provider_by_name(self.provider_name)
        if not spec:
            return
        if not spec.env_key:
            return
        os.environ.setdefault(spec.env_key, api_key)

    def _get_client(self):
        if self._client is None:
            kwargs = {"api_key": self.api_key}
            if self.api_base:
                kwargs["base_url"] = self.api_base
            self._client = Anthropic(**kwargs)
        return self._client

    @staticmethod
    def _sanitize_empty_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")

            if isinstance(content, str) and not content:
                clean = dict(msg)
                clean["content"] = None if (msg.get("role") == "assistant" and msg.get("tool_calls")) else "(empty)"
                result.append(clean)
                continue

            if isinstance(content, list):
                filtered = [
                    item for item in content
                    if not (
                        isinstance(item, dict)
                        and item.get("type") in ("text", "input_text", "output_text")
                        and not item.get("text")
                    )
                ]
                if len(filtered) != len(content):
                    clean = dict(msg)
                    if filtered:
                        clean["content"] = filtered
                    elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                        clean["content"] = None
                    else:
                        clean["content"] = "(empty)"
                    result.append(clean)
                    continue

            if isinstance(content, dict):
                clean = dict(msg)
                clean["content"] = [content]
                result.append(clean)
                continue

            result.append(msg)
        return result

    @staticmethod
    def _sanitize_request_messages(
        messages: list[dict[str, Any]],
        allowed_keys: frozenset[str],
    ) -> list[dict[str, Any]]:
        sanitized = []
        for msg in messages:
            clean = {k: v for k, v in msg.items() if k in allowed_keys}
            if clean.get("role") == "assistant" and "content" not in clean:
                clean["content"] = None
            sanitized.append(clean)
        return sanitized

    @classmethod
    def _is_transient_error(cls, content: str | None) -> bool:
        err = (content or "").lower()
        return any(marker in err for marker in cls._TRANSIENT_ERROR_MARKERS)

    @classmethod
    def _is_image_unsupported_error(cls, content: str | None) -> bool:
        err = (content or "").lower()
        return any(marker in err for marker in cls._IMAGE_UNSUPPORTED_MARKERS)

    @staticmethod
    def _strip_image_content(messages: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        found = False
        result = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                new_content = []
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "image_url":
                        new_content.append({"type": "text", "text": "[image omitted]"})
                        found = True
                    else:
                        new_content.append(b)
                result.append({**msg, "content": new_content})
            else:
                result.append(msg)
        return result if found else None

    async def _safe_chat(self, **kwargs: Any) -> LLMResponse:
        try:
            return await self.chat(**kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return LLMResponse(content=f"Error calling LLM: {exc}", finish_reason="error")

    async def chat_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: object = _SENTINEL,
        temperature: object = _SENTINEL,
        reasoning_effort: object = _SENTINEL,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        if max_tokens is self._SENTINEL:
            max_tokens = self.generation.max_tokens
        if temperature is self._SENTINEL:
            temperature = self.generation.temperature
        if reasoning_effort is self._SENTINEL:
            reasoning_effort = self.generation.reasoning_effort

        kw: dict[str, Any] = dict(
            messages=messages, tools=tools, model=model,
            max_tokens=max_tokens, temperature=temperature,
            reasoning_effort=reasoning_effort, tool_choice=tool_choice,
        )

        for attempt, delay in enumerate(self._CHAT_RETRY_DELAYS, start=1):
            response = await self._safe_chat(**kw)

            if response.finish_reason != "error":
                return response

            if not self._is_transient_error(response.content):
                if self._is_image_unsupported_error(response.content):
                    stripped = self._strip_image_content(messages)
                    if stripped is not None:
                        logger.warning("Model does not support image input, retrying without images")
                        return await self._safe_chat(**{**kw, "messages": stripped})
                return response

            logger.warning(
                "LLM transient error (attempt {}/{}), retrying in {}s: {}",
                attempt, len(self._CHAT_RETRY_DELAYS), delay,
                (response.content or "")[:120].lower(),
            )
            await asyncio.sleep(delay)

        return await self._safe_chat(**kw)

    def _convert_messages(self, messages: list[dict[str, Any]]) -> tuple[str | None, list[dict]]:
        system = None
        anthropic_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content")
            else:
                anthropic_msg = {"role": msg["role"], "content": msg.get("content", "")}
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    anthropic_msg["tool_calls"] = msg["tool_calls"]
                if msg.get("role") == "tool":
                    anthropic_msg["role"] = "user"
                    tool_result = {
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": msg.get("content", ""),
                    }
                    anthropic_msg["content"] = [tool_result]
                anthropic_messages.append(anthropic_msg)
        return system, anthropic_messages

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict] | None:
        if not tools:
            return None
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object"}),
                })
        return anthropic_tools if anthropic_tools else None

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        try:
            client = self._get_client()
            system, anthropic_messages = self._convert_messages(messages)
            anthropic_tools = self._convert_tools(tools)

            kwargs: dict[str, Any] = {
                "model": model or self.default_model,
                "messages": anthropic_messages,
                "max_tokens": max(max_tokens, 1),
                "temperature": temperature,
            }
            if system:
                kwargs["system"] = system
            if anthropic_tools:
                kwargs["tools"] = anthropic_tools
            if tool_choice:
                if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
                    kwargs["tool_choice"] = {"type": "tool", "name": tool_choice["function"]["name"]}
                elif tool_choice == "auto":
                    kwargs["tool_choice"] = {"type": "auto"}
                elif tool_choice == "none":
                    kwargs["tool_choice"] = {"type": "none"}

            if reasoning_effort:
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": 4096}

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: client.messages.create(**kwargs))

            content = None
            reasoning_content = None
            thinking_blocks = None
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content = block.text
                elif block.type == "thinking":
                    reasoning_content = block.thinking
                    thinking_blocks = [{"type": "thinking", "thinking": block.thinking}]
                elif block.type == "tool_use":
                    tool_calls.append(ToolCallRequest(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    ))

            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                }

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason="stop" if not tool_calls else "tool_calls",
                usage=usage,
                reasoning_content=reasoning_content,
                thinking_blocks=thinking_blocks,
            )

        except Exception as e:
            logger.error("Anthropic API error: {}", e)
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )


