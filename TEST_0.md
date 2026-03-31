# TEST 0: Guard + Repair Auto-Recovery

## Goal
Verify tinyagent self-healing: Guard detects crash, Repair fixes code, archives logs.

## Step 1: Inject Bug

```bash
# Edit tinyagent/loop.py line 285
sed -i 's/_COMMAND_HANDLERS.get/_COMMAND_HAND.get/' tinyagent/loop.py

# Verify
grep -n "_COMMAND_HAND" tinyagent/loop.py
```

## Step 2: Start Guard

```bash
pkill -9 -f tinyagent
rm -f ~/.tinyagent/workspace/crash_*.log

python -m tinyagent.tinyagent_guard ~/.tinyagent/workspace /workspaces/tinyagent &
```

## Step 3: Trigger Crash

```bash
python -m tinyagent.cli message "test" &
```

## Step 4: Verify (wait 30s)

```bash
# Guard detected exit
tail ~/.tinyagent/workspace/GUARD_LOG

# Crash archived
ls ~/.tinyagent/workspace/history_crash/

# Repair archived
ls ~/.tinyagent/workspace/repair_history/

# Code fixed
grep "285:" tinyagent/loop.py
```

## Expected

| Check | Result |
|-------|--------|
| Crash file | Moved to `history_crash/` |
| Code fix | `_COMMAND_HAND` → `_COMMAND_HANDLERS` |
| Guard restart | `[restart] delay=3s` in GUARD_LOG |
| Repair log | `repair_history/repair_*.log` created |

## Notes

- Guard会在检测到进程退出或心跳超时时启动repair
- Repair完成后，guard会重启agent
- 如果连续3次crash，guard会执行git rollback
- 测试前确保代码目录是git仓库且工作区干净

## Step 5: Cleanup

```bash
# Stop all tinyagent processes
pkill -9 -f tinyagent

# Remove test artifacts
rm -rf ~/.tinyagent/workspace/crash_*.log
rm -rf ~/.tinyagent/workspace/GUARD_LOG
rm -rf ~/.tinyagent/workspace/HEARTBEAT
rm -rf ~/.tinyagent/workspace/history_crash/
rm -rf ~/.tinyagent/workspace/repair_history/
rm -rf ~/.tinyagent/workspace/logs/
```
