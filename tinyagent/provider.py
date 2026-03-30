import asyncio
from dataclasses import dataclass, field
from typing import Any

from anthropic import Anthropic
from loguru import logger


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]

    def to_anthropic_format(self) -> dict[str, Any]:
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.arguments}


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
        return bool(self.tool_calls)


class LLMProvider:
    _RETRY_DELAYS = (1, 2, 4)

    def __init__(
        self,
        api_key: str,
        api_base: str | None = None,
        default_model: str = "claude-opus-4-5",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ):
        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        kwargs = {"api_key": api_key}
        if api_base:
            kwargs["base_url"] = api_base
        self._client = Anthropic(**kwargs)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        reasoning_effort: str | None = None,
        tool_choice: Any = None,
    ) -> LLMResponse:
        # Convert messages
        system = None
        anthropic_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system = msg.get("content")
            else:
                anthropic_messages.append({"role": msg["role"], "content": msg.get("content", "")})


        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature or self.temperature,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
                kwargs["tool_choice"] = {"type": "tool", "name": tool_choice["function"]["name"]}
            elif tool_choice == "auto":
                kwargs["tool_choice"] = {"type": "auto"}

        if reasoning_effort or self.reasoning_effort:
            effective_max = max_tokens or self.max_tokens
            budget = min(4096, effective_max - 1)
            if budget >= 1024:
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: self._client.messages.create(**kwargs))

        content = None
        reasoning = None
        tool_calls = []
        thinking_blocks: list[dict] = []

        for block in response.content:
            if block.type == "text":
                content = block.text
            elif block.type == "thinking":
                reasoning = block.thinking
                thinking_blocks.append({"type": "thinking", "thinking": block.thinking})
            elif block.type == "tool_use":
                tool_calls.append(ToolCallRequest(id=block.id, name=block.name, arguments=block.input))

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            reasoning_content=reasoning,
            thinking_blocks=thinking_blocks or None,
        )

    async def chat_with_retry(self, **kwargs) -> LLMResponse:
        """Chat with simple retry for rate limits."""
        last_error = None
        for delay in self._RETRY_DELAYS:
            try:
                return await self.chat(**kwargs)
            except Exception as e:
                last_error = e
                logger.warning("LLM error, retrying in {}s: {}", delay, str(e)[:100])
                await asyncio.sleep(delay)
        raise last_error
