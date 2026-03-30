"""
Web Search Skill - Independent Implementation

This is a standalone web search tool that can be loaded as a skill.
It does not depend on the tinyagent core package.
"""
import asyncio
import os
from typing import Any

import httpx


# Tool metadata
NAME = "web_search"
DESCRIPTION = "Search the web. Returns titles, URLs, and snippets."
PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query"},
        "count": {"type": "integer", "description": "Results (1-10)", "minimum": 1, "maximum": 10},
    },
    "required": ["query"],
}


class WebSearchTool:
    """Search the web using configured provider."""

    def __init__(self, provider: str = "brave", api_key: str | None = None, proxy: str | None = None):
        self.provider = provider
        self.api_key = api_key or os.environ.get("BRAVE_API_KEY", "")
        self.proxy = proxy

    async def execute(self, query: str, count: int = 5, **kwargs: Any) -> str:
        n = min(max(count, 1), 10)
        if self.provider == "brave":
            return await self._search_brave(query, n)
        elif self.provider == "duckduckgo":
            return await self._search_duckduckgo(query, n)
        elif self.provider == "tavily":
            return await self._search_tavily(query, n)
        elif self.provider == "jina":
            return await self._search_jina(query, n)
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
            return self._format_results(query, items, n)
        except Exception as e:
            return f"Error: {e}"

    async def _search_tavily(self, query: str, n: int) -> str:
        api_key = os.environ.get("TAVILY_API_KEY", "")
        try:
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"query": query, "max_results": n},
                    timeout=15.0,
                )
                r.raise_for_status()
            return self._format_results(query, r.json().get("results", []), n)
        except Exception as e:
            return f"Error: {e}"

    async def _search_jina(self, query: str, n: int) -> str:
        api_key = os.environ.get("JINA_API_KEY", "")
        try:
            headers = {"Accept": "application/json", "Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(proxy=self.proxy) as client:
                r = await client.get(
                    "https://s.jina.ai/",
                    params={"q": query},
                    headers=headers,
                    timeout=15.0,
                )
                r.raise_for_status()
            data = r.json().get("data", [])[:n]
            items = [
                {"title": d.get("title", ""), "url": d.get("url", ""), "content": d.get("content", "")[:500]}
                for d in data
            ]
            return self._format_results(query, items, n)
        except Exception as e:
            return f"Error: {e}"

    async def _search_duckduckgo(self, query: str, n: int) -> str:
        try:
            from ddgs import DDGS

            ddgs = DDGS(timeout=10)
            raw = await asyncio.to_thread(ddgs.text, query, max_results=n)
            if not raw:
                return f"No results for: {query}"
            items = [
                {"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")}
                for r in raw
            ]
            return self._format_results(query, items, n)
        except Exception as e:
            return f"Error: DuckDuckGo search failed ({e})"

    def _format_results(self, query: str, items: list[dict[str, Any]], n: int) -> str:
        if not items:
            return f"No results for: {query}"
        lines = [f"Results for: {query}\n"]
        for i, item in enumerate(items[:n], 1):
            title = item.get("title", "")
            snippet = item.get("content", "") or item.get("description", "")
            lines.append(f"{i}. {title}\n   {item.get('url', '')}")
            if snippet:
                lines.append(f"   {snippet}")
        return "\n".join(lines)


# Factory function for skill loader
def create_tool(config: dict[str, Any] | None = None) -> WebSearchTool:
    """Create tool instance with optional config."""
    cfg = config or {}
    return WebSearchTool(
        provider=cfg.get("provider", "brave"),
        api_key=cfg.get("api_key"),
        proxy=cfg.get("proxy"),
    )


# For direct testing
if __name__ == "__main__":
    import asyncio

    async def test():
        tool = create_tool()
        result = await tool.execute("python programming", count=3)
        print(result)

    asyncio.run(test())
