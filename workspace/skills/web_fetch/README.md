# Web Fetch Skill

Fetch and extract readable content from URLs.

## Features

- Extract content from HTML pages
- Convert HTML to markdown or plain text
- JSON content support
- Automatic content extraction using Jina AI (fallback to readability-lxml)

## Configuration

```yaml
# skill.yaml
name: web_fetch
version: 1.0.0
tool: tool.py
config:
  max_chars: 50000
  proxy: null
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `JINA_API_KEY` | Optional Jina AI API key for better extraction |

## Dependencies

```bash
pip install httpx readability-lxml
```

## Usage

```python
from tool import create_tool

tool = create_tool()
result = await tool.execute("https://example.com", extractMode="markdown")
```

## Extract Modes

- **markdown** (default): Convert HTML to markdown
- **text**: Extract plain text only

## Response Format

```json
{
  "url": "original-url",
  "finalUrl": "resolved-url",
  "status": 200,
  "extractor": "jina|readability|json|raw",
  "truncated": false,
  "length": 1234,
  "untrusted": true,
  "text": "[External content...]\n\n# Title\nContent..."
}
```

## Tool Schema

- **name**: `web_fetch`
- **parameters**:
  - `url` (string, required): URL to fetch
  - `extractMode` (string, optional): "markdown" or "text", default "markdown"
  - `maxChars` (integer, optional): Maximum characters to return
