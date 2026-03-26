---
name: memory
description: Two-layer memory system with grep-based recall.
always: true
---

# Memory

- `memory/MEMORY.md` — Long-term facts (preferences, project context). Always loaded.
- `memory/HISTORY.md` — Append-only event log. NOT loaded; search with grep.

## Search History

```bash
# Linux/macOS
grep -i "keyword" memory/HISTORY.md

# Windows
findstr /i "keyword" memory\HISTORY.md
```

## Update MEMORY.md

Write important facts immediately:
- User preferences ("I prefer dark mode")
- Project context ("The API uses OAuth2")
- Relationships ("Alice is the project lead")

## Auto-consolidation

Old conversations are auto-summarized to HISTORY.md when sessions grow large.
