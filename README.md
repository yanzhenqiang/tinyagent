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
    └─► Start Agent ──► Monitor heartbeat
        │
        ├─ Crash ──► Write crash_*.log ──► Back to Repair
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
