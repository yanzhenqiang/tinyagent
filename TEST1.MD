# TEST1: 对话回放与分叉验证系统测试

## 测试目标

验证 `/replay` 和 `/replayandmodify` 功能的正确性。

## 前置条件

```bash
# 1. 确保tinyagent正常运行
python -m tinyagent message "/help" --workspace workspace

# 2. 确保已有对话历史
# 如果没有，先创建一些对话：
python -m tinyagent message "你好" --workspace workspace
python -m tinyagent message "使用bash工具执行echo test" --workspace workspace
python -m tinyagent message "当前时间是多少" --workspace workspace
```

## 测试1: 基础Replay功能

### 步骤1: 执行Replay

```bash
# 从第2个回合开始回放
python -m tinyagent message "/replay 2" --workspace workspace
```

### 预期结果

```
🔄 Replay initiated from turn 2

Forked session: base:message:replay_a1b2c3d4
Original messages: 15
Replay messages: 15

Comparison:
- System prompt: ✓ Match
- Skills: ✓ Match
- Tools: ✓ Match
- Message sequence: ✓ Match
- Final output: ✓ Semantically equivalent

Judge LLM verdict:
{
  "equivalent": true,
  "confidence": 95,
  "reasoning": "Both traces show identical tool usage and semantically equivalent responses...",
  "differences": []
}
```

### 验证点

- [ ] Replay session被创建
- [ ] Trace文件保存到 workspace/replays/
- [ ] 原trace和replay trace都被记录
- [ ] 评判LLM返回一致的结果

---

## 测试2: ReplayAndModify - Real模式

### 步骤1: 执行带修改的Replay

```bash
# 从第2个回合开始，应用real修改
python -m tinyagent message "/replayandmodify 2 real" --workspace workspace
```

### 预期行为

系统会：
1. Fork session
2. 修改某个tool结果（如将"test"改为"MODIFIED_TEST"）
3. 执行replay
4. 对比两个trace

### 预期结果

```
🔄 Replay with modification (mode: real)

Modification applied:
- Tool: bash
- Original: "test"
- Modified: "MODIFIED_TEST"

Comparison:
- System prompt: ✓ Match
- Skills: ✓ Match
- Tools: ✓ Match
- Message sequence: ✗ Different (tool result modified)
- Final output: ✗ Different

Judge LLM verdict:
{
  "equivalent": false,
  "confidence": 90,
  "reasoning": "Tool result was explicitly modified, leading to different downstream behavior...",
  "differences": [
    "Tool 'bash' result differs: 'test' vs 'MODIFIED_TEST'",
    "Final assistant response differs accordingly"
  ]
}
```

### 验证点

- [ ] 修改被正确应用
- [ ] Judge判定为不一致
- [ ] 差异原因被正确识别

---

## 测试3: ReplayAndModify - Fake模式

### 步骤1: 执行带无关修改的Replay

```bash
# 从第2个回合开始，应用fake修改
python -m tinyagent message "/replayandmodify 2 fake" --workspace workspace
```

### 预期行为

系统会：
1. Fork session
2. 添加无影响的修改（如给system prompt加注释）
3. 执行replay
4. 对比两个trace

### 预期结果

```
🔄 Replay with modification (mode: fake)

Modification applied:
- Added harmless comment to system prompt
- No functional changes

Comparison:
- System prompt: ⚠ Different (non-functional)
- Skills: ✓ Match
- Tools: ✓ Match
- Message sequence: ✓ Match
- Final output: ✓ Semantically equivalent

Judge LLM verdict:
{
  "equivalent": true,
  "confidence": 98,
  "reasoning": "Modification was purely cosmetic (comment addition) with no impact on behavior...",
  "differences": [
    "System prompt contains additional comment (non-functional)"
  ]
}
```

### 验证点

- [ ] 无影响的修改被应用
- [ ] Judge判定为一致
- [ ] 正确识别修改是非功能性的

---

## 测试4: VerifyTrace命令

### 步骤1: 获取两个trace ID

```bash
# 先执行两个replay产生trace
python -m tinyagent message "/replay 2" --workspace workspace
# 记录返回的 trace_id_1

python -m tinyagent message "/replay 2" --workspace workspace
# 记录返回的 trace_id_2
```

### 步骤2: 手动比较

```bash
python -m tinyagent message "/verifytrace a1b2c3d4 e5f6g7h8" --workspace workspace
```

### 预期结果

```
🔍 Comparing traces a1b2c3d4 vs e5f6g7h8

Trace a1b2c3d4:
- Messages: 15
- Tool calls: 2
- Final output: "输出内容..."

Trace e5f6g7h8:
- Messages: 15
- Tool calls: 2
- Final output: "输出内容..."

Judge LLM verdict:
{
  "equivalent": true,
  "confidence": 94,
  "reasoning": "Both traces are semantically equivalent...",
  "differences": []
}
```

---

## 测试5: 边界条件

### 测试5.1: 超出范围的回合数

```bash
python -m tinyagent message "/replay 999" --workspace workspace
```

**预期**: 返回错误 "Session only has X turns, cannot replay from turn 999"

### 测试5.2: 无效的回合数

```bash
python -m tinyagent message "/replay 0" --workspace workspace
python -m tinyagent message "/replay -1" --workspace workspace
python -m tinyagent message "/replay abc" --workspace workspace
```

**预期**: 返回错误 "Invalid turn number"

### 测试5.3: 空Session

```bash
# 新session没有历史
python -m tinyagent message "/new" --workspace workspace
python -m tinyagent message "/replay 1" --workspace workspace
```

**预期**: 返回错误 "No conversation history to replay"

---

## 测试6: 文件持久化验证

### 步骤1: 执行Replay

```bash
python -m tinyagent message "/replay 2" --workspace workspace
# 记录返回的 replay_id
```

### 步骤2: 验证文件创建

```bash
ls -la workspace/replays/
# 应看到:
# <replay_id>.json           - ReplaySession元数据
# <replay_id>_original.json  - 原trace
# <replay_id>_replay.json    - replay trace
```

### 步骤3: 验证文件内容

```bash
cat workspace/replays/<replay_id>.json | jq .
```

**预期内容**:
```json
{
  "id": "a1b2c3d4",
  "source_session": "base:message",
  "fork_point": 2,
  "mode": "normal",
  "created_at": "2026-04-01T10:00:00",
  "original_trace_path": "...",
  "replay_trace_path": "...",
  "comparison_result": {...}
}
```

---

## 测试7: 多轮对话后的Replay

### 步骤1: 创建复杂对话

```bash
python -m tinyagent message "/new" --workspace workspace
python -m tinyagent message "列出当前目录文件" --workspace workspace
python -m tinyagent message "读取第一个文件的内容" --workspace workspace
python -m tinyagent message "总结这个文件" --workspace workspace
python -m tinyagent message "有什么修改建议吗" --workspace workspace
```

### 步骤2: 从不同回合Replay

```bash
# 从第3回合开始（中间分叉）
python -m tinyagent message "/replay 3" --workspace workspace
```

### 验证点

- [ ] Fork正确截取了前2回合
- [ ] 从第3回合user消息开始replay
- [ ] 后续的tool调用重新执行
- [ ] 最终输出与原trace可比

---

## 清理

```bash
# 测试完成后清理
rm -rf workspace/replays/
pkill -9 -f tinyagent
```

---

## 测试8: 复杂多轮任务（Coding Task）

### 目标

测试一个复杂的多轮开发任务，涉及多次工具调用和人工干预。

### 步骤1: 创建复杂任务

```bash
# 新建session
python -m tinyagent message "/new" --workspace workspace

# 第一轮：创建项目结构
python -m tinyagent message "创建一个Python项目，包含以下结构：
- src/calculator.py (实现加减乘除)
- tests/test_calculator.py (单元测试)
- README.md (项目说明)
请使用bash工具创建文件和目录" --workspace workspace

# 第二轮：检查实现
python -m tinyagent message "读取 src/calculator.py 检查实现是否正确" --workspace workspace

# 第三轮：人工干预（模拟发现问题）
python -m tinyagent message "这个实现缺少除零保护，请修复并添加错误处理" --workspace workspace

# 第四轮：运行测试
python -m tinyagent message "运行测试验证修复是否正确" --workspace workspace

# 第五轮：收尾
python -m tinyagent message "总结一下这个项目的最终状态" --workspace workspace
```

### 步骤2: 从中间回合Replay

```bash
# 从第3回合开始replay（人工干预点）
python -m tinyagent message "/replay 3" --workspace workspace
```

### 预期结果

- Replay session 正确创建
- 从第3回合（人工干预）开始重新执行
- 模型重新生成对干预的响应
- 最终输出与原始trace语义一致

### 验证点

- [ ] 项目结构正确创建
- [ ] 代码修改被重新应用
- [ ] 测试通过
- [ ] Replay trace 与 original trace 语义一致

---

## 通过标准

所有测试必须通过：
- [x] 测试1: 基础Replay
- [x] 测试2: Real模式修改
- [x] 测试3: Fake模式修改
- [x] 测试4: VerifyTrace
- [x] 测试5: 边界条件
- [x] 测试6: 文件持久化
- [x] 测试7: 复杂对话
- [ ] 测试8: 复杂多轮任务（Coding Task）
