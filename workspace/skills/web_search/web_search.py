"""
Web Search Skill Template

This is a template skill for web search functionality.
Copy this file to your workspace and customize as needed.
"""
import asyncio
import os
from typing import Any

import httpx
from loguru import logger

from tinyagent.tools.base import Tool


class WebSearchTool(Tool):
    """Search the web using configured provider."""

    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10},
        },
        "required": ["query"],
    }

    def __init__(self, provider: str = "brave", api_key: str | None = None, proxy: str | None = None):
        self.provider = provider
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.proxy = proxy

    async def execute(self, query: str, count: int = 5, **kwargs: Any) -> str:
        n = min(max(count, 1), 10)
        if self.provider == "brave":
            return await self._search_brave(query, n)
        else:
            return f"Error: unknown provider '{self.provider}'"

    async def _search_brave(self, query: str, n: int) -> str:
        try:
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": n},
                    headers={"Accept": "application/json", "X-Subscription-Token": self.api_key},
                    timeout=10.0,
                )
                r.raise_for_status()
            data = r.json()
            items = data.get("web", {}).get("results", [])
            if not items:
                return f"No results for: {query}"
            lines = [f"Results for: {query}\n"]
            for i, item in enumerate(items[:n], 1):
                lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
            return "\n".join(lines)
        except Exception as e:
            logger.error("Search failed: {}", e)
            return f"Error: {e}"
