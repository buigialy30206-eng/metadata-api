"""
URL Metadata Extractor API
Extracts Open Graph / Twitter Card / meta tags from any URL.
"""
import re, subprocess, time, threading
from typing import Optional
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import time as _t, threading as _th
_rl_win, _rl_max, _rl_hits, _rl_lk = 60, 60, {}, _th.Lock()

async def _rate_limit(request):
    from fastapi import Request, HTTPException
    ip = (request.headers.get('X-Forwarded-For','') or request.headers.get('X-Real-IP','') or (request.client.host if request.client else '127.0.0.1')).split(',')[0].strip()
    now = _t.time()
    with _rl_lk:
        e = _rl_hits.get(ip)
        if e:
            if now - e['s'] > _rl_win: e['s'], e['c'] = now, 1
            else:
                e['c'] += 1
                if e['c'] > _rl_max: raise HTTPException(429, 'Too many requests')
        else: _rl_hits[ip] = {'s': now, 'c': 1}
    return True

app = FastAPI(title="URL Metadata Extractor API", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# Cache
_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 600  # 10 min


class Metadata(BaseModel):
    url: str
    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    favicon: Optional[str] = None
    site_name: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_image: Optional[str] = None
    twitter_card: Optional[str] = None
    error: Optional[str] = None


def fetch_html(url: str) -> str:
    cmd = ["curl", "-sL", "--connect-timeout", "6", "--max-time", "10",
           "-H", "User-Agent: Mozilla/5.0", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, Exception):
        return ""


def extract_meta(html: str, name: str) -> Optional[str]:
    try:
        m = re.search(rf'<meta[^>]+(?:name|property)=["\']{name}["\']',
                      html, re.I)
        if m:
            m2 = re.search(r'content=["\']([^"\']+)["\']', html[m.start():], re.I)
            if m2:
                return m2.group(1)
        m = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\']',
                      html, re.I)
        if m:
            tail = html[m.end():m.end()+200]
            m2 = re.search(rf'(?:name|property)=["\']{name}["\']', tail, re.I)
            if m2:
                return m.group(1)
    except:
        pass
    return None


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok", "cache_size": len(_cache)}


@app.get("/")
async def root():
    return {"service": "URL Metadata Extractor API", "version": "1.1.0"}


@app.get("/extract", response_model=Metadata)
async def extract(url: str = Query(..., description="URL to extract metadata from")):
    # Check cache
    with _cache_lock:
        entry = _cache.get(url)
        if entry and time.time() - entry["ts"] < CACHE_TTL:
            return Metadata(**entry["data"])

    html = fetch_html(url)
    if not html:
        result = Metadata(url=url, error="Could not fetch URL")
        return result

    favicon = None
    try:
        m = re.search(r'<link[^>]+rel=["\'](?:shortcut )?icon["\']',
                      html, re.I)
        if m:
            tail = html[m.start():m.start()+300]
            m2 = re.search(r'href=["\']([^"\']+)["\']', tail, re.I)
            if m2:
                favicon = m2.group(1)
                if favicon.startswith("/"):
                    from urllib.parse import urljoin
                    favicon = urljoin(url, favicon)
    except:
        pass

    title_match = re.search(r"<title>([^<]+)</title>", html, re.I)
    
    result = Metadata(
        url=url,
        title=extract_meta(html, "title") or (title_match.group(1) if title_match else None),
        description=extract_meta(html, "description"),
        image=extract_meta(html, "image"),
        favicon=favicon,
        site_name=extract_meta(html, "og:site_name"),
        og_title=extract_meta(html, "og:title"),
        og_description=extract_meta(html, "og:description"),
        og_image=extract_meta(html, "og:image"),
        twitter_card=extract_meta(html, "twitter:card"),
    )

    # Save cache
    with _cache_lock:
        _cache[url] = {"data": result.model_dump(), "ts": time.time()}
        if len(_cache) > 500:
            oldest = min(_cache, key=lambda k: _cache[k]["ts"])
            del _cache[oldest]

    return result
