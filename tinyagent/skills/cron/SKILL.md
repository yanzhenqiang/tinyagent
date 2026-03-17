---
name: cron
description: Schedule reminders and recurring tasks.
---

# Cron

## Examples

```python
# Reminder
cron(action="add", message="Time to take a break!", every_seconds=1200)

# Recurring task
cron(action="add", message="Check GitHub stars", every_seconds=600)

# One-time
cron(action="add", message="Meeting", at="2024-01-15T09:00:00")

# Cron expression
cron(action="add", message="Standup", cron_expr="0 9 * * 1-5", tz="America/Vancouver")

# List/remove
cron(action="list")
cron(action="remove", job_id="abc123")
```

## Time Expressions

| User says | Parameters |
|-----------|------------|
| every 20 minutes | every_seconds: 1200 |
| every hour | every_seconds: 3600 |
| every day at 8am | cron_expr: "0 8 * * *" |
| weekdays at 5pm | cron_expr: "0 17 * * 1-5" |
| at a specific time | at: ISO datetime |
