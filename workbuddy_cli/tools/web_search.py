"""
First-Class DeepSeek Official Search (`/v1/tools/search`) & Fetch (`/v1/tools/fetch`)
with Multi-Tier Keyless Fallback (DuckDuckGo Lite / Bing CN) for workbuddy-cli.

Architecture:
  - Tier 1 (Primary First-Class Citizen): DeepSeek Official Native Search & Fetch REST API
    * `POST https://api.deepseek.com/v1/tools/search`
      (`{"query": str, "count": int, "ori_question": str, "need_content": bool}`)
      Returns `rerank_score`, `authority`, `site_name`, `date`, `snippet`, and 600-800 word `summary`!
    * `POST https://api.deepseek.com/v1/tools/fetch`
      (`{"url": str}`) -> Returns clean Markdown `{"title": str, "content": str}`!
    * Authenticates directly with the same DeepSeek API Key configured in `~/.workbuddy-cli/config.json`!
  - Tier 2 (Keyless Fallback 1): DuckDuckGo Lite (`https://lite.duckduckgo.com/lite/`)
  - Tier 3 (Keyless Fallback 2): Bing CN (`https://cn.bing.com/search`)
"""

import html
import os
import re
from urllib.parse import unquote, urlparse, parse_qs
from typing import List, Dict, Any, Optional

import httpx

from ..config import WorkBuddyConfig


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _resolve_deepseek_key(explicit_key: Optional[str] = None) -> str:
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    cfg = WorkBuddyConfig.load()
    if cfg.api_key and cfg.api_key.startswith("sk-"):
        return cfg.api_key.strip()
    return (
        os.environ.get("WORKBUDDY_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or ""
    ).strip()


def _clean_html_text(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", raw_html)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _unwrap_ddg_url(raw_url: str) -> str:
    u = html.unescape(raw_url or "").strip()
    if "duckduckgo.com/l/?" in u:
        parsed = urlparse("https:" + u if u.startswith("//") else u)
        qs = parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])
    return u


def search_deepseek_official(
    query: str,
    api_key: str,
    max_results: int = 5,
    ori_question: str = "",
    need_content: bool = False,
    timeout: float = 15.0,
) -> List[Dict[str, Any]]:
    """
    Calls DeepSeek's official native search API: `POST https://api.deepseek.com/v1/tools/search`.
    Supports `site:`, `-site:`, `lang:`, `after:`, `before:` operators.
    """
    payload: Dict[str, Any] = {
        "query": query[:128],
        "count": max(1, min(max_results, 20)),
        "need_content": bool(need_content),
    }
    if ori_question:
        payload["ori_question"] = ori_question[:128]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post("https://api.deepseek.com/v1/tools/search", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

    results: List[Dict[str, Any]] = []
    for item in (data.get("results") or [])[:max_results]:
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "site_name": item.get("site_name", ""),
                "date": item.get("date", ""),
                "authority": item.get("authority"),
                "rerank_score": round(float(item.get("rerank_score") or 0.0), 4),
                "snippet": item.get("snippet", ""),
                "summary": item.get("summary", ""),
                "content": item.get("content", "") if need_content else "",
                "engine": "deepseek-official-search",
            }
        )
    return results


def fetch_deepseek_official(url: str, api_key: str, max_chars: int = 8000, timeout: float = 20.0) -> Dict[str, Any]:
    """
    Calls DeepSeek's official native page extractor: `POST https://api.deepseek.com/v1/tools/fetch`.
    Returns clean Markdown `title` and `content`.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post("https://api.deepseek.com/v1/tools/fetch", headers=headers, json={"url": url})
        resp.raise_for_status()
        data = resp.json()

    content = data.get("content") or ""
    return {
        "status": "ok",
        "engine": "deepseek-official-fetch",
        "url": url,
        "title": data.get("title") or url,
        "content": content[:max_chars],
        "total_chars": len(content),
    }


def search_ddg_lite(query: str, max_results: int = 6, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Queries DuckDuckGo Lite (`https://lite.duckduckgo.com/lite/`) without any API key."""
    results: List[Dict[str, Any]] = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
        resp = client.post("https://lite.duckduckgo.com/lite/", data={"q": query})
        resp.raise_for_status()
        page = resp.text

    a_tags = re.findall(r"(<a[^>]*result-link[^>]*>[\s\S]*?</a>)", page, flags=re.IGNORECASE)
    snippets = re.findall(
        r"<td[^>]*class=[\"\x27]result-snippet[\"\x27][^>]*>([\s\S]*?)</td>",
        page,
        flags=re.IGNORECASE,
    )

    for idx, a_tag in enumerate(a_tags):
        if len(results) >= max_results:
            break
        href_m = re.search(r"href=[\"\x27]([^\"\x27]+)[\"\x27]", a_tag, flags=re.IGNORECASE)
        if not href_m:
            continue
        url = _unwrap_ddg_url(href_m.group(1))
        if not url.startswith("http"):
            continue
        title = _clean_html_text(a_tag)
        snippet = _clean_html_text(snippets[idx]) if idx < len(snippets) else ""
        if title:
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "summary": snippet,
                    "engine": "duckduckgo-lite",
                }
            )
    return results


def search_bing_cn(query: str, max_results: int = 6, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Queries Bing CN (`https://cn.bing.com/search`) as keyless fallback."""
    results: List[Dict[str, Any]] = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
        resp = client.get("https://cn.bing.com/search", params={"q": query})
        resp.raise_for_status()
        page = resp.text

    blocks = re.findall(r'<li class="b_algo"[^>]*>([\s\S]*?)</li>', page, flags=re.IGNORECASE)
    for block in blocks:
        if len(results) >= max_results:
            break
        m_a = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>', block, flags=re.IGNORECASE)
        if not m_a:
            continue
        url = html.unescape(m_a.group(1)).strip()
        title = _clean_html_text(m_a.group(2))
        body_without_h2 = re.sub(r"<h2[^>]*>[\s\S]*?</h2>", "", block, flags=re.IGNORECASE)
        snippet = _clean_html_text(body_without_h2)[:240]
        if title and url.startswith("http"):
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "summary": snippet,
                    "engine": "bing-cn",
                }
            )
    return results


def search_web(
    query: str,
    max_results: int = 5,
    ori_question: str = "",
    need_content: bool = False,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Multi-tier resilient web search:
      1. DeepSeek Official Search API (`https://api.deepseek.com/v1/tools/search`) — First-Class Citizen!
      2. DuckDuckGo Lite (`https://lite.duckduckgo.com/lite/`) — Keyless fallback 1
      3. Bing CN (`https://cn.bing.com/search`) — Keyless fallback 2
    """
    q = (query or "").strip()
    if not q:
        return {"query": "", "engine": "none", "results": [], "error": "Empty query"}

    errors = []
    ds_key = _resolve_deepseek_key(api_key)
    if ds_key:
        try:
            res_ds = search_deepseek_official(
                q,
                api_key=ds_key,
                max_results=max_results,
                ori_question=ori_question or q,
                need_content=need_content,
            )
            if res_ds:
                return {
                    "query": q,
                    "engine": "deepseek-official-search",
                    "count": len(res_ds),
                    "results": res_ds,
                }
        except Exception as exc:
            errors.append(f"deepseek-official-search: {exc}")

    try:
        res_ddg = search_ddg_lite(q, max_results=max_results)
        if res_ddg:
            return {"query": q, "engine": "duckduckgo-lite", "count": len(res_ddg), "results": res_ddg}
    except Exception as exc:
        errors.append(f"duckduckgo-lite: {exc}")

    try:
        res_bing = search_bing_cn(q, max_results=max_results)
        if res_bing:
            return {"query": q, "engine": "bing-cn", "count": len(res_bing), "results": res_bing}
    except Exception as exc:
        errors.append(f"bing-cn: {exc}")

    return {"query": q, "engine": "failed", "count": 0, "results": [], "errors": errors}


def fetch_web_page(url: str, max_chars: int = 6000, api_key: Optional[str] = None, timeout: float = 15.0) -> Dict[str, Any]:
    """
    Fetches a web page using:
      1. DeepSeek Official Fetch API (`https://api.deepseek.com/v1/tools/fetch`) -> clean Markdown
      2. Direct HTTP GET + HTML tag stripper fallback
    """
    target = (url or "").strip()
    if not target.startswith("http"):
        target = "https://" + target.lstrip("/")

    ds_key = _resolve_deepseek_key(api_key)
    if ds_key:
        try:
            res_ds = fetch_deepseek_official(target, api_key=ds_key, max_chars=max_chars, timeout=timeout)
            if res_ds.get("content"):
                return res_ds
        except Exception:
            pass

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=DEFAULT_HEADERS) as client:
            resp = client.get(target)
            resp.raise_for_status()
            raw = resp.text

        title_m = re.search(r"<title[^>]*>([\s\S]*?)</title>", raw, flags=re.IGNORECASE)
        title = _clean_html_text(title_m.group(1)) if title_m else target

        cleaned_html = re.sub(
            r"<(script|style|noscript|svg|nav|footer|header|iframe)[^>]*>[\s\S]*?</\1>",
            " ",
            raw,
            flags=re.IGNORECASE,
        )
        text = _clean_html_text(cleaned_html)
        return {
            "status": "ok",
            "engine": "direct-http",
            "url": str(resp.url),
            "title": title,
            "content": text[:max_chars],
            "total_chars": len(text),
        }
    except Exception as exc:
        return {"status": "error", "url": target, "error": str(exc), "content": ""}
