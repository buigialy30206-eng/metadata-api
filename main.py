"""
URL Metadata Extractor API
Extracts Open Graph / Twitter Card / meta tags from any URL.
"""

import re, subprocess, json as _json
from typing import Optional

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="URL Metadata Extractor API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}



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


def fetch_html(url: str) -> str:
    cmd = ["curl", "-sL", "--connect-timeout", "8", "--max-time", "12",
           "-H", "User-Agent: Mozilla/5.0", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def extract_meta(html: str, name: str) -> Optional[str]:
    # <meta name="xxx" content="yyy">
    m = re.search(rf'<meta[^>]+(?:name|property)=["\']{name}["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
    if m: return m.group(1)
    # <meta content="yyy" ... name="xxx">
    m = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\']{name}["\']', html, re.I)
    if m: return m.group(1)
    return None


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "URL Metadata Extractor API", "version": "1.0.0"}


@app.get("/extract", response_model=Metadata)
async def extract(url: str = Query(..., description="URL to extract metadata from")):
    html = fetch_html(url)
    if not html:
        raise HTTPException(502, "Could not fetch URL")

    # Favicon
    favicon = None
    m = re.search(r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)["\']', html, re.I)
    if m:
        favicon = m.group(1)
        if favicon.startswith("/"):
            from urllib.parse import urljoin
            favicon = urljoin(url, favicon)

    title_match = re.search(r"<title>([^<]+)</title>", html, re.I)
    return Metadata(
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
