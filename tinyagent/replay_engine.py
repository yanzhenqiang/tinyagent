#!/usr/bin/env python3
"""
对话回放与分叉验证系统

实现对话历史的回放、分叉和一致性验证。
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from tinyagent.session import Session, SessionManager
from tinyagent.provider import LLMProvider
from tinyagent.context import ContextBuilder


@dataclass
class Trace:
    """对话Trace，记录完整的对话过程"""
    messages: list[dict]  # 完整消息序列
    responses: list[str]  # LLM每一次响应
    tool_calls: list[dict]  # 工具调用记录
    final_output: str
    system_prompt: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Trace":
        return cls(**data)


@dataclass
class ComparisonResult:
    """两个Trace的比较结果"""
    equivalent: bool
    confidence: int  # 0-100
    reasoning: str
    differences: list[str]
    system_match: bool
    skills_match: bool
    tools_match: bool
    messages_match: bool


@dataclass
class ReplaySession:
    """回放会话元数据"""
    id: str
    source_session: str
    fork_point: int
    mode: str  # "normal", "real", "fake"
    modification: Optional[dict]
    original_trace: Trace
    replay_trace: Trace
    comparison: ComparisonResult
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_session": self.source_session,
            "fork_point": self.fork_point,
            "mode": self.mode,
            "modification": self.modification,
            "original_trace": self.original_trace.to_dict(),
            "replay_trace": self.replay_trace.to_dict(),
            "comparison": asdict(self.comparison),
            "created_at": self.created_at,
        }


class TraceComparator:
    """Trace比较器"""

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def compare(self, trace1: Trace, trace2: Trace) -> ComparisonResult:
        """对比两个trace，返回初步比较结果"""
        differences = []

        # 1. System prompt比较
        system_match = trace1.system_prompt == trace2.system_prompt
        if not system_match:
            differences.append("System prompt differs")

        # 2. 消息数量比较
        messages_match = len(trace1.messages) == len(trace2.messages)
        if not messages_match:
            differences.append(f"Message count differs: {len(trace1.messages)} vs {len(trace2.messages)}")

        # 3. Tool calls比较
        tool_calls_match = len(trace1.tool_calls) == len(trace2.tool_calls)
        if not tool_calls_match:
            differences.append(f"Tool call count differs: {len(trace1.tool_calls)} vs {len(trace2.tool_calls)}")

        # 4. 最终输出比较（简单的字符串比较）
        output_match = trace1.final_output == trace2.final_output

        # 初步判定：所有简单检查都通过才算一致
        equivalent = system_match and messages_match and tool_calls_match and output_match

        return ComparisonResult(
            equivalent=equivalent,
            confidence=100 if equivalent else 50,
            reasoning="Surface-level comparison" if equivalent else "Surface differences detected",
            differences=differences,
            system_match=system_match,
            skills_match=True,  # Skills包含在system中
            tools_match=tool_calls_match,
            messages_match=messages_match,
        )

    async def judge_with_llm(self, trace1: Trace, trace2: Trace) -> ComparisonResult:
        """使用LLM进行深度语义比较"""
        judge_prompt = """You are a conversation trace analysis expert.

Compare the following two conversation traces and determine if they are semantically equivalent.

Trace 1 (Original):
{trace1_summary}

Trace 2 (Replay):
{trace2_summary}

Full Trace 1 Messages:
{trace1_messages}

Full Trace 2 Messages:
{trace2_messages}

Analyze dimensions:
1. Tool usage patterns (are the same tools called with equivalent parameters?)
2. Response semantics (are the responses conveying the same meaning?)
3. Reasoning consistency (do both traces follow similar logic?)

Important: Responses don't need to be word-for-word identical, but should convey equivalent meaning and perform equivalent actions.

Output valid JSON only:
{{
  "equivalent": true/false,
  "confidence": 0-100,
  "reasoning": "Detailed analysis...",
  "differences": ["difference 1", "difference 2"]
}}"""

        trace1_summary = self._summarize_trace(trace1)
        trace2_summary = self._summarize_trace(trace2)
        trace1_messages = self._format_messages(trace1.messages)
        trace2_messages = self._format_messages(trace2.messages)

        prompt = judge_prompt.format(
            trace1_summary=trace1_summary,
            trace2_summary=trace2_summary,
            trace1_messages=trace1_messages,
            trace2_messages=trace2_messages,
        )

        try:
            response = await self.provider.chat_with_retry(
                messages=[{"role": "user", "content": prompt}],
                model=self.provider.default_model,
                max_tokens=2000,
            )

            # Parse JSON response
            content = response.content.strip()
            # Extract JSON if wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            return ComparisonResult(
                equivalent=result.get("equivalent", False),
                confidence=result.get("confidence", 0),
                reasoning=result.get("reasoning", ""),
                differences=result.get("differences", []),
                system_match=True,  # Judge focuses on semantic equivalence
                skills_match=True,
                tools_match=result.get("equivalent", False),
                messages_match=result.get("equivalent", False),
            )
        except Exception as e:
            logger.error("LLM judging failed: {}", e)
            # Fall back to surface comparison
            return self.compare(trace1, trace2)

    def _summarize_trace(self, trace: Trace) -> str:
        """生成trace摘要"""
        return f"""- Messages: {len(trace.messages)}
- Tool calls: {len(trace.tool_calls)}
- Final output: {trace.final_output[:200]}..."""

    def _format_messages(self, messages: list[dict]) -> str:
        """格式化消息列表用于LLM输入"""
        lines = []
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = str(content)[:300]
            else:
                content = str(content)[:300]
            lines.append(f"[{i}] {role}: {content}")
        return "\n".join(lines)


class ReplayEngine:
    """回放引擎"""

    def __init__(self, workspace: Path, provider: LLMProvider):
        self.workspace = workspace
        self.provider = provider
        self.session_manager = SessionManager(workspace)
        self.context_builder = ContextBuilder(workspace)
        self.comparator = TraceComparator(provider)
        self.replays_dir = workspace / "replays"
        self.replays_dir.mkdir(parents=True, exist_ok=True)

    def _generate_replay_id(self, source_key: str, fork_point: int) -> str:
        """生成replay session ID"""
        data = f"{source_key}:{fork_point}:{datetime.now().isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()[:8]

    def fork_session(self, source_key: str, fork_point: int) -> tuple[Session, Session]:
        """
        创建分叉session

        Args:
            source_key: 原session key
            fork_point: 从第几个回合开始分叉（1-indexed）

        Returns:
            (原session, 新fork的session)
        """
        source = self.session_manager.get_or_create(source_key)

        if not source.messages:
            raise ValueError("Source session has no messages")

        if fork_point < 1 or fork_point > len(source.messages):
            raise ValueError(f"Invalid fork point {fork_point}, session has {len(source.messages)} messages")

        # 创建新的replay session
        replay_id = self._generate_replay_id(source_key, fork_point)
        new_key = f"{source_key}:replay_{replay_id}"
        forked = Session(key=new_key)

        # 复制前 fork_point-1 个消息（保留上下文）
        # 注意：这里的"回合"指的是user-assistant交互对
        # 需要找到第 fork_point 个user消息的位置
        user_message_indices = [
            i for i, m in enumerate(source.messages)
            if m.get("role") == "user"
        ]

        if fork_point > len(user_message_indices):
            raise ValueError(f"Session only has {len(user_message_indices)} user turns")

        # 截取到第 fork_point 个user消息之前的所有消息
        if fork_point == 1:
            # 从最开始，不复制历史
            cutoff = 0
        else:
            cutoff = user_message_indices[fork_point - 1]

        forked.messages = source.messages[:cutoff]
        forked.created_at = datetime.now()

        return source, forked

    def apply_modification(self, trace: Trace, mode: str) -> tuple[Trace, dict]:
        """
        应用修改（real/fake模式）

        Args:
            trace: 原始trace
            mode: "real" 或 "fake"

        Returns:
            (修改后的trace, 修改描述)
        """
        if mode == "real":
            # 真实修改：修改最后一个tool的结果
            modified_trace = Trace(
                messages=trace.messages.copy(),
                responses=trace.responses.copy(),
                tool_calls=trace.tool_calls.copy(),
                final_output=trace.final_output,
                system_prompt=trace.system_prompt,
            )

            # 找到最后一个tool_result并修改
            for i in range(len(modified_trace.messages) - 1, -1, -1):
                msg = modified_trace.messages[i]
                if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                    for item in msg["content"]:
                        if item.get("type") == "tool_result":
                            original = item.get("content", "")
                            modified = f"[MODIFIED] {original}"
                            item["content"] = modified
                            return modified_trace, {
                                "type": "tool_result",
                                "index": i,
                                "original": original,
                                "modified": modified,
                            }

            # 如果没有tool result，修改assistant消息
            for i in range(len(modified_trace.messages) - 1, -1, -1):
                if modified_trace.messages[i].get("role") == "assistant":
                    original = modified_trace.messages[i].get("content", "")
                    modified = f"[MODIFIED] {original}"
                    modified_trace.messages[i]["content"] = modified
                    modified_trace.final_output = modified
                    return modified_trace, {
                        "type": "assistant_message",
                        "index": i,
                        "original": original,
                        "modified": modified,
                    }

            return modified_trace, {"type": "none", "reason": "No modifiable content found"}

        elif mode == "fake":
            # 假修改：给system prompt添加注释
            modified_trace = Trace(
                messages=trace.messages.copy(),
                responses=trace.responses.copy(),
                tool_calls=trace.tool_calls.copy(),
                final_output=trace.final_output,
                system_prompt=trace.system_prompt + "\n<!-- This is a harmless comment for testing replay functionality -->",
            )

            # 也修改messages中的system消息
            for msg in modified_trace.messages:
                if msg.get("role") == "system":
                    msg["content"] = msg.get("content", "") + "\n<!-- Harmless test comment -->"
                    break

            return modified_trace, {
                "type": "system_comment",
                "description": "Added harmless comment to system prompt",
            }

        else:
            return trace, {"type": "none"}

    async def replay_session(
        self,
        forked: Session,
        original_messages: list[dict],
        apply_mod: bool = False,
        modification_mode: str = "normal",
    ) -> Trace:
        """
        执行回放

        Args:
            forked: 分叉后的session
            original_messages: 原始消息序列（用于对比）
            apply_mod: 是否应用修改
            modification_mode: 修改模式

        Returns:
            Replay后的trace
        """
        # TODO: 实现实际的LLM回放
        # 这里先返回一个模拟的trace
        # 实际实现需要：
        # 1. 从fork_point开始，用相同的user消息重新调用LLM
        # 2. 记录所有响应和tool调用
        # 3. 构建新的trace

        # 模拟实现：复制原trace但标记为replay
        replay_trace = Trace(
            messages=forked.messages.copy(),
            responses=[],
            tool_calls=[],
            final_output="[Replay - TODO: implement actual replay logic]",
            system_prompt="",
        )

        return replay_trace

    async def run_replay(
        self,
        source_key: str,
        fork_point: int,
        mode: str = "normal",
    ) -> ReplaySession:
        """
        运行完整的回放流程

        Args:
            source_key: 原session key
            fork_point: 从第几个回合开始分叉
            mode: "normal", "real", 或 "fake"

        Returns:
            ReplaySession包含原trace、replay trace和比较结果
        """
        # 1. Fork session
        source, forked = self.fork_session(source_key, fork_point)

        # 2. 构建原trace
        original_trace = Trace(
            messages=source.messages.copy(),
            responses=[],  # TODO: 从历史中提取
            tool_calls=[],  # TODO: 从历史中提取
            final_output=source.messages[-1].get("content", "") if source.messages else "",
            system_prompt=self.context_builder.build_system_prompt(),
        )

        # 3. 应用修改（如果需要）
        modification = None
        modified_original = original_trace
        if mode in ("real", "fake"):
            modified_original, modification = self.apply_modification(original_trace, mode)

        # 4. 执行replay
        replay_trace = await self.replay_session(
            forked,
            original_trace.messages,
            apply_mod=mode in ("real", "fake"),
            modification_mode=mode,
        )

        # 5. 比较trace
        if mode == "normal":
            comparison = await self.comparator.judge_with_llm(original_trace, replay_trace)
        else:
            # real/fake模式：比较修改后的original和replay
            comparison = await self.comparator.judge_with_llm(modified_original, replay_trace)

        # 6. 创建ReplaySession
        replay_id = self._generate_replay_id(source_key, fork_point)
        replay_session = ReplaySession(
            id=replay_id,
            source_session=source_key,
            fork_point=fork_point,
            mode=mode,
            modification=modification,
            original_trace=original_trace,
            replay_trace=replay_trace,
            comparison=comparison,
        )

        # 7. 保存到文件
        self._save_replay(replay_session)

        return replay_session

    def _save_replay(self, replay: ReplaySession) -> None:
        """保存replay session到文件"""
        # 主元数据文件
        meta_path = self.replays_dir / f"{replay.id}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(replay.to_dict(), f, indent=2, ensure_ascii=False)

        # 单独的trace文件（便于查看）
        orig_path = self.replays_dir / f"{replay.id}_original.json"
        with open(orig_path, "w", encoding="utf-8") as f:
            json.dump(replay.original_trace.to_dict(), f, indent=2, ensure_ascii=False)

        replay_path = self.replays_dir / f"{replay.id}_replay.json"
        with open(replay_path, "w", encoding="utf-8") as f:
            json.dump(replay.replay_trace.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info("Replay saved to {}", self.replays_dir / replay.id)

    def load_replay(self, replay_id: str) -> Optional[ReplaySession]:
        """加载replay session"""
        meta_path = self.replays_dir / f"{replay_id}.json"
        if not meta_path.exists():
            return None

        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return ReplaySession(
            id=data["id"],
            source_session=data["source_session"],
            fork_point=data["fork_point"],
            mode=data["mode"],
            modification=data.get("modification"),
            original_trace=Trace.from_dict(data["original_trace"]),
            replay_trace=Trace.from_dict(data["replay_trace"]),
            comparison=ComparisonResult(**data["comparison"]),
            created_at=data["created_at"],
        )

    def list_replays(self) -> list[dict]:
        """列出所有replay session"""
        replays = []
        for path in self.replays_dir.glob("*.json"):
            if "_original" in path.name or "_replay" in path.name:
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                replays.append({
                    "id": data["id"],
                    "source_session": data["source_session"],
                    "fork_point": data["fork_point"],
                    "mode": data["mode"],
                    "created_at": data["created_at"],
                    "equivalent": data["comparison"]["equivalent"],
                })
            except Exception:
                continue
        return sorted(replays, key=lambda x: x["created_at"], reverse=True)
