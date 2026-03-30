# Web Search Skill

Search the web using various providers.

## Usage

```python
from tinyagent.tools.registry import ToolRegistry
from skills.web_search import WebSearchTool

registry = ToolRegistry()
registry.register(WebSearchTool(
    provider="brave",
    api_key="your-api-key"  # or set BRAVE_API_KEY env var
))
```

## Configuration

- `provider`: Search provider (default: "brave")
- `api_key`: API key for the provider
- `proxy`: Optional proxy URL

## Environment Variables

- `BRAVE_API_KEY`: Brave Search API key
