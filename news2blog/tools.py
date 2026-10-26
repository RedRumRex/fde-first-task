"""The researcher's two tools: web search (Tavily) and page fetch (httpx + trafilatura, Tavily extract fallback)."""
import os
from typing import Any
from urllib.parse import urlparse

import httpx

from . import config
from .runlog import RunLogger

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host.split(":")[0]
    for p in ("www.", "amp.", "m."):
        if host.startswith(p):
            host = host[len(p):]
    return host


def _tavily():
    from tavily import TavilyClient

    key = os.getenv("TAVILY_API_KEY")
    return TavilyClient(api_key=key) if key else None


def _extract(html: str, url: str) -> dict[str, Any]:
    import trafilatura

    doc = trafilatura.bare_extraction(html, url=url, with_metadata=True, favor_recall=True)
    if doc is None:
        return {}
    if hasattr(doc, "as_dict"):
        doc = doc.as_dict()
    return dict(doc)


def fetch_page(url: str, log: RunLogger | None = None, node: str = "researcher") -> dict[str, Any]:
    """Fetch a URL and return clean article text. Never raises; returns ok=False with an error instead."""
    result: dict[str, Any] = {"url": url, "ok": False, "title": "", "date": "", "text": "", "error": "", "via": "httpx"}
    try:
        r = httpx.get(
            url,
            headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*"},
            follow_redirects=True,
            timeout=25,
        )
        result["final_url"] = str(r.url)
        if r.status_code >= 400:
            result["error"] = f"HTTP {r.status_code}"
        else:
            doc = _extract(r.text, str(r.url))
            result.update(title=doc.get("title") or "", date=doc.get("date") or "", text=(doc.get("text") or "").strip())
    except Exception as e:  # DNS failure, timeout, TLS...
        result["error"] = f"{type(e).__name__}: {e}"[:300]

    if len(result["text"]) < config.MIN_ARTICLE_CHARS:
        # Fallback: Tavily's extractor often gets past bot walls that block plain httpx
        tv = _tavily()
        if tv is not None:
            try:
                ex = tv.extract(urls=[url], format="text")
                if log:
                    log.add_tavily(1)
                items = ex.get("results") or []
                if items and len(items[0].get("raw_content") or "") >= config.MIN_ARTICLE_CHARS:
                    result.update(text=items[0]["raw_content"].strip(), via="tavily_extract", error="")
            except Exception as e:
                result["error"] = (result["error"] + f" | tavily_extract: {e}")[:300]

    result["text"] = result["text"][: config.MAX_SOURCE_CHARS]
    result["ok"] = len(result["text"]) >= config.MIN_ARTICLE_CHARS
    if not result["ok"] and not result["error"]:
        result["error"] = f"extracted only {len(result['text'])} chars"
    if log:
        log.event(node, "fetch", f"{'OK ' if result['ok'] else 'FAIL'} {url} ({len(result['text'])} chars via {result['via']}) {result['error']}",
                  url=url, ok=result["ok"], chars=len(result["text"]), via=result["via"], error=result["error"])
    return result


def search_web(
    query: str,
    log: RunLogger | None = None,
    exclude_domains: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    max_results: int = 5,
    node: str = "researcher",
) -> list[dict[str, Any]]:
    tv = _tavily()
    if tv is None:
        raise RuntimeError("TAVILY_API_KEY is not set")
    kwargs: dict[str, Any] = dict(query=query, search_depth="basic", max_results=max_results)
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains
    if start_date and end_date:
        kwargs.update(start_date=start_date, end_date=end_date)
    try:
        res = tv.search(**kwargs)
    except Exception as e:
        if "start_date" in kwargs:  # older plans / API versions: retry without the date window
            kwargs.pop("start_date"), kwargs.pop("end_date")
            res = tv.search(**kwargs)
        else:
            raise e
    if log:
        log.add_tavily(1)
    hits = [
        {"url": h.get("url"), "title": h.get("title"), "snippet": (h.get("content") or "")[:200], "published_date": h.get("published_date", "")}
        for h in res.get("results", [])
    ]
    if log:
        log.event(node, "search", f"'{query}' -> {len(hits)} hits", query=query, hits=[h["url"] for h in hits])
    return hits
