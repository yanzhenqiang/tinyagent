# DESIGN1: 对话回放与分叉验证系统

## 概述

实现一个高级功能，允许从任意回合开始"回放"对话历史，创建对话分叉，并验证两个对话trace的一致性。

## 背景

当前上下文由以下部分组成：
1. **System Prompt**: 基础系统指令
2. **Skills**: 技能定义（动态加载到system中）
3. **Tools**: 工具定义（传递给LLM的函数定义）
4. **Messages**: 对话历史（user/assistant/tool）

## 核心概念

### 1. 对话Trace

一个完整的对话Trace包含：
```
Trace = {
  system_prompt: str,
  skills: List[Skill],
  tools: List[Tool],
  messages: List[Message],
  responses: List[Response]  // LLM的每一次回复
}
```

### 2. 回放（Replay）

从第N个回合开始，使用相同的system/skills/tools，重新执行后续对话。

关键假设：**如果问题描述明确，回放的trace应该与原trace等价**

### 3. 分叉（Fork）

创建一个新的session，复制原session的前N-1个回合，然后分叉执行。

## 功能设计

### 命令1: `/replay <n>`

从第n个回合开始回放对话。

**流程：**
1. 获取当前session的历史
2. 截取前n-1个回合作为前缀
3. 创建新的replay session（fork）
4. 从第n个user消息开始，重新调用LLM
5. 对比原trace和replay trace

**输出：**
- 原trace的摘要
- replay trace的摘要
- 一致性判定结果

### 命令2: `/replayandmodify <n> <mode>`

在回放时进行修改，验证模型是否能检测到变化。

**mode参数：**
- `real`: 真实修改（如修改某个tool的结果）
  - 期望：两个trace不一致
- `fake`: 假修改（如添加无影响的注释）
  - 期望：两个trace一致

**流程：**
1. 同`/replay <n>`的前3步
2. 根据mode应用修改器
3. 执行replay
4. 调用评判LLM判定一致性

### 命令3: `/verifytrace <trace1_id> <trace2_id>`

将两个trace交给专门的评判LLM进行比较。

**评判Prompt设计：**
```
你是一个对话trace分析专家。

请比较以下两个对话trace，判断它们是否语义等价。

Trace 1:
[trace1内容]

Trace 2:
[trace2内容]

分析维度：
1. 系统行为是否一致（调用的工具、参数）
2. 最终输出是否语义等价（不需要逐字相同）
3. 思考过程是否逻辑一致

输出格式：
{
  "equivalent": true/false,
  "confidence": 0-100,
  "reasoning": "详细分析...",
  "differences": ["差异1", "差异2"]
}
```

## 技术实现

### 1. 数据结构

```python
@dataclass
class ReplaySession:
    id: str  # sha-like id
    source_session: str  # 原session key
    fork_point: int  # 从第几个回合分叉
    original_trace: Trace
    replay_trace: Trace
    created_at: datetime
    mode: str  # "normal", "real", "fake"
    modification: Optional[Dict]  # 修改描述

@dataclass
class Trace:
    messages: List[dict]  # 完整消息序列
    responses: List[str]  # LLM每一次响应
    tool_calls: List[dict]  # 工具调用记录
    final_output: str
```

### 2. 存储

- ReplaySession保存到 `workspace/replays/<id>.json`
- Trace详情保存到 `workspace/replays/<id>_original.json` 和 `<id>_replay.json`

### 3. 核心类

```python
class ReplayEngine:
    def fork_session(self, source_key: str, n: int) -> Session:
        """创建分叉session"""

    def replay(self, forked: Session, original_messages: List[dict]) -> Trace:
        """执行回放"""

    def apply_modification(self, trace: Trace, mode: str) -> Trace:
        """应用修改（real/fake模式）"""

class TraceComparator:
    def compare(self, trace1: Trace, trace2: Trace) -> ComparisonResult:
        """对比两个trace"""

    def judge_with_llm(self, trace1: Trace, trace2: Trace) -> JudgementResult:
        """使用LLM进行评判"""
```

### 4. 集成到AgentLoop

添加命令处理器：
```python
async def _cmd_replay(self, msg: InboundMessage) -> OutboundMessage:
    # 解析参数
    parts = msg.content.split()
    n = int(parts[1])

    # 创建replay
    engine = ReplayEngine(self.workspace, self.provider)
    result = await engine.run_replay(
        source_session=msg.session_key,
        fork_point=n,
        mode="normal"
    )

    # 返回结果
    return OutboundMessage(...)
```

## 一致性判定标准

### 强一致（Strong Equivalence）
- 所有工具调用完全相同（包括参数）
- 所有响应逐字相同

### 语义一致（Semantic Equivalence）
- 工具调用逻辑相同（允许参数顺序差异）
- 最终输出语义等价（不需要逐字相同）
- 思考过程逻辑一致

默认使用**语义一致**作为判定标准。

## 应用场景

1. **回归测试**: 验证修改后对话行为是否改变
2. **确定性验证**: 验证相同输入是否产生相同输出
3. **影响分析**: 评估某个修改对对话的影响范围
4. **A/B测试**: 对比不同prompt/system的效果
