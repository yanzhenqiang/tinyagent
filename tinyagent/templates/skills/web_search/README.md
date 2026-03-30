# Web Search Skill

Search the web using various providers.

## Supported Providers

- **brave** (default) - Brave Search API
- **duckduckgo** - DuckDuckGo (no API key required)
- **tavily** - Tavily Search API
- **jina** - Jina AI Search

## Configuration

```yaml
# skill.yaml
name: web_search
version: 1.0.0
tool: tool.py
config:
  provider: brave
  api_key: ""  # Or set BRAVE_API_KEY env var
  proxy: null
```

## Environment Variables

| Variable | Provider | Description |
|----------|----------|-------------|
| `BRAVE_API_KEY` | brave | Brave Search API key |
| `TAVILY_API_KEY` | tavily | Tavily API key |
| `JINA_API_KEY` | jina | Jina AI API key |

## Usage

```python
from tool import create_tool

tool = create_tool({"provider": "brave"})
result = await tool.execute("search query", count=5)
```

## Tool Schema

- **name**: `web_search`
- **parameters**:
  - `query` (string, required): Search query
  - `count` (integer, optional): Number of results (1-10), default 5
