## Architecture

Agent always run and self-repair

### Bootstrap Flow

```
Guard (supervisor)
    │
    ├─► Start Repair Agent ──► Wait 5min or exit
    │   - Check workspace/crash_*.log
    │   - Try fix with bash tool
    │   - Move crash to history_crash/
    │
    └─► Start Agent ──► Monitor heartbeat (5s interval)
        │
        ├─ No heartbeat 30s ──► Kill ──► Write crash_*.log ──► Back to Repair
        │
        ├─ Crash ──► Write crash_*.log ──► Back to Repair
        │
        ├─ 3 crashes ──► Git rollback ──► Back to Repair
        │
        └─ User exit ──► Done
```

### Crash Handling

**Crash detection:**
- Code exceptions (AttributeError, TypeError, etc.) → write `workspace/crash_*.log`
- User interrupt (Ctrl+C) → no crash log
- Config errors → no crash log

**Repair process:**
- Guard launches `repair.py` before each Agent start
- Repair has only `bash` tool, uses LLM to analyze and fix
- Repair logs all actions to `workspace/logs/repair.log`
- After repair (success or fail), crash moves to `history_crash/`

### Guard Heartbeat

Agent writes heartbeat every 5s to `workspace/HEARTBEAT`

Guard checks:
- Heartbeat timeout 30s → Agent hang → Kill → Crash log → Repair
- Process exit with code → Write crash log → Repair
- 3 consecutive crashes → Git rollback → Repair
- Clean exit (code 0) → Shutdown

### Directory Structure

```
workspace/
├── crash_20250326_080635.log    # fresh crash (waiting for repair)
├── history_crash/                # archived crashes
│   └── crash_20250325_....log
└── logs/
    └── repair.log               # repair actions log
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `tinyagent chat` | Interactive chat mode (Terminal channel) |
| `tinyagent message "task"` | One-shot message mode |
| `tinyagent gateway` | Start Feishu gateway |
| `tinyagent gateway --guard` | Start Guard supervisor (production) |


其实这个工程是一个状态机，没准用状态机更容易实现呢?
其实可以写成一个agent loop别的啥也没有
这个agent loop有两套promt
一套修复的只有bash
一套负责的
如果有crash文件就加载crash的

飞书这个进程也是agent loop启动的
feishu在另外一个进程
这样人写code就更少了
这样guard只负责拉起agent loop就够了对吧