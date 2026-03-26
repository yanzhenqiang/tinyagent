---
name: weather
description: Get current weather and forecasts (no API key required).
homepage: https://wttr.in/:help
metadata: {"tinyagent":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# Weather

## wttr.in (primary)

```bash
# Quick
curl -s "wttr.in/London?format=3"

# Compact
curl -s "wttr.in/London?format=%l:+%c+%t+%h+%w"

# Full forecast
curl -s "wttr.in/London?T"
```

Format codes: `%c` condition · `%t` temp · `%h` humidity · `%w` wind · `%l` location

Tips:
- Spaces: `wttr.in/New+York`
- Airport: `wttr.in/JFK`
- Units: `?m` (metric) `?u` (USCS)

## Open-Meteo (fallback)

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true"
```
