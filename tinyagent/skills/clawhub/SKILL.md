---
name: clawhub
description: Search and install skills from ClawHub, the public skill registry.
homepage: https://clawhub.ai
metadata: {"tinyagent":{"emoji":"🦞"}}
---

# ClawHub

Public skill registry for AI agents.

## Usage

```bash
# Search
npx --yes clawhub@latest search "web scraping" --limit 5

# Install
npx --yes clawhub@latest install <slug> --workdir ~/.tinyagent/workspace

# Update all
npx --yes clawhub@latest update --all --workdir ~/.tinyagent/workspace

# List installed
npx --yes clawhub@latest list --workdir ~/.tinyagent/workspace
```

Requires Node.js. No API key needed for search/install.
