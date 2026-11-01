"""
Wurmz API by Nat — scrape https://wurmz.net
Endpoints:
  GET /                  health
  GET /search?q=         search series
  GET /popular?range=    all|today|3d|7d|30d
  GET /latest            latest updates
  GET /list              semua-komik (optional sort=new)
  GET /series/{type}/{slug}   detail + chapters + synopsis + genres
  GET /chapter/{type}/{slug}/{num}   chapter images
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote, unquote

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except Exception:
    HAS_BS4 = False

BASE = "https://wurmz.net"
CDN_HOSTS = ("cdn.voratoon.com", "voratoon.com")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
    "Referer": BASE + "/",
}

BAD_IMG = (
    "logo", "icon", "avatar", "emoji", "favicon", "banner", "promo",
    "adsense", "doubleclick", "statcounter", "histats", "pixel",
    "button", "badge", "widget", "facebook", "twitter", "paypal",
    "donate", "sponsor", "1x1", "blank.gif", "loading", "spinner",
    "placeholder", "ads-", "/ads/", "googlesyndication", "cloudflare",
)

app = FastAPI(title="Wurmz API by Nat", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _abs(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return BASE + url
    return url


def _clean_img(url: str) -> Optional[str]:
    url = _abs(url)
    if not url.startswith("http"):
        return None
    low = url.lower()
    if any(b in low for b in BAD_IMG):
        return None
    return url


def _cover_from_slug(type_: str, slug: str) -> str:
    return f"{BASE}/covers/{type_}__{slug}.webp"


def _parse_series_from_html(html: str) -> list:
    """Extract unique series cards from list pages."""
    items = []
    seen = set()
    # /detail/{type}/{slug} optionally with chapter
    for m in re.finditer(
        r"/detail/(manga|manhwa|manhua)/([a-z0-9-]+)(?:/chapter/([\d.]+))?",
        html,
        re.I,
    ):
        type_, slug, ch = m.group(1).lower(), m.group(2).lower(), m.group(3)
        key = f"{type_}/{slug}"
        if key in seen:
            # update latest chapter if present
            if ch:
                for it in items:
                    if it["id"] == key and not it.get("latest_chapter"):
                        it["latest_chapter"] = ch
            continue
        seen.add(key)
        # title near cover path or from slug
        title = slug.replace("-", " ").title()
        cover = _cover_from_slug(type_, slug)
        # try better cover from html
        cm = re.search(
            rf"/covers/{type_}__{re.escape(slug)}\.(?:webp|jpg|jpeg|png)",
            html,
            re.I,
        )
        if cm:
            cover = _abs(cm.group(0))
        items.append(
            {
                "id": key,
                "type": type_,
                "slug": slug,
                "title": title,
                "cover": cover,
                "latest_chapter": ch,
                "url": f"{BASE}/detail/{type_}/{slug}",
            }
        )
    return items


def _upgrade_titles(html: str, items: list) -> list:
    """Try to map slug -> human title from heading text in HTML."""
    if not HAS_BS4:
        return items
    try:
        soup = BeautifulSoup(html, "html.parser")
        # links with meaningful text
        title_map = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"/detail/(manga|manhwa|manhua)/([a-z0-9-]+)", href)
            if not m:
                continue
            key = f"{m.group(1).lower()}/{m.group(2).lower()}"
            text = a.get_text(" ", strip=True)
            if text and len(text) > 3 and not re.match(r"^ch\.?\s*\d", text, re.I):
                if key not in title_map or len(text) > len(title_map[key]):
                    title_map[key] = text
        for it in items:
            if it["id"] in title_map:
                it["title"] = title_map[it["id"]]
    except Exception:
        pass
    return items


async def _get(url: str, timeout: float = 28.0) -> httpx.Response:
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers=HEADERS
    ) as client:
        r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(r.status_code, f"Upstream {r.status_code}: {url}")
        return r


@app.get("/")
async def root():
    return {
        "ok": True,
        "name": "Wurmz API by Nat",
        "version": "1.0.0",
        "source": BASE,
        "endpoints": [
            "/search?q=",
            "/popular?range=all|today|3d|7d|30d",
            "/latest",
            "/list?sort=new",
            "/series/{type}/{slug}",
            "/chapter/{type}/{slug}/{num}",
        ],
    }


@app.get("/latest")
async def latest():
    r = await _get(BASE + "/")
    items = _upgrade_titles(r.text, _parse_series_from_html(r.text))
    return {"ok": True, "count": len(items), "results": items}


@app.get("/list")
async def list_all(sort: str = Query("new", description="new or default")):
    url = f"{BASE}/semua-komik"
    if sort:
        url += f"?sort={quote(sort)}"
    r = await _get(url)
    items = _upgrade_titles(r.text, _parse_series_from_html(r.text))
    return {"ok": True, "count": len(items), "results": items}


@app.get("/popular")
async def popular(
    range: str = Query("all", description="all|today|3d|7d|30d"),
):
    range = (range or "all").lower()
    if range not in ("all", "today", "3d", "7d", "30d"):
        range = "all"
    r = await _get(f"{BASE}/populer?range={range}")
    items = _upgrade_titles(r.text, _parse_series_from_html(r.text))
    return {"ok": True, "range": range, "count": len(items), "results": items}


@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    q = q.strip()
    r = await _get(f"{BASE}/search?q={quote(q)}")
    items = _upgrade_titles(r.text, _parse_series_from_html(r.text))
    # soft filter by query token
    tokens = [t for t in re.split(r"\s+", q.lower()) if t]
    if tokens:
        ranked = []
        for it in items:
            blob = (it["title"] + " " + it["slug"]).lower()
            score = sum(1 for t in tokens if t in blob)
            if score:
                ranked.append((score, it))
        if ranked:
            ranked.sort(key=lambda x: -x[0])
            items = [x[1] for x in ranked]
    return {"ok": True, "q": q, "count": len(items), "results": items}


@app.get("/series/{type_}/{slug}")
async def series_detail(type_: str, slug: str):
    type_ = type_.lower().strip()
    slug = slug.lower().strip()
    if type_ not in ("manga", "manhwa", "manhua"):
        raise HTTPException(400, "type must be manga|manhwa|manhua")
    url = f"{BASE}/detail/{type_}/{slug}"
    r = await _get(url)
    html = r.text

    title = slug.replace("-", " ").title()
    synopsis = ""
    genres: list[str] = []
    status = ""
    author = ""
    cover = _cover_from_slug(type_, slug)
    chapters = []

    # JSON-ish genre array in RSC payload
    gm = re.search(r'"genre"\s*:\s*\[(.*?)\]', html)
    if gm:
        genres = re.findall(r'"([^"]+)"', gm.group(1))

    # /genre/Name links
    for g in re.findall(r"/genre/([A-Za-z0-9_\-+%]+)", html):
        name = unquote(g).replace("+", " ").strip()
        if name and name not in genres:
            genres.append(name)

    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True) or title
        # synopsis
        syn = None
        for h in soup.find_all(["h2", "h3"]):
            if "sinopsis" in (h.get_text() or "").lower():
                syn = h.find_next(["p", "div"])
                break
        if syn:
            synopsis = syn.get_text(" ", strip=True)
        if not synopsis:
            # meta description
            md = soup.find("meta", attrs={"name": "description"})
            if md and md.get("content"):
                synopsis = md["content"].strip()
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            cover = _abs(og["content"])
        # status chip
        text_all = soup.get_text(" ", strip=True)
        if re.search(r"\bOngoing\b", text_all, re.I):
            status = "Ongoing"
        elif re.search(r"\bCompleted\b", text_all, re.I):
            status = "Completed"
        # author line "Oleh ..."
        om = re.search(r"Oleh\s+(.+?)(?:·|Diperbarui|$)", text_all)
        if om:
            author = om.group(1).strip(" ·")

    # chapter list
    seen_ch = set()
    for m in re.finditer(
        rf"/detail/{type_}/{re.escape(slug)}/chapter/([\d.]+)",
        html,
        re.I,
    ):
        num = m.group(1)
        if num in seen_ch:
            continue
        seen_ch.add(num)
        chapters.append(
            {
                "id": f"{type_}/{slug}/{num}",
                "number": num,
                "url": f"{BASE}/detail/{type_}/{slug}/chapter/{num}",
                "api": f"/chapter/{type_}/{slug}/{num}",
            }
        )

    # sort chapters numeric desc (site default often newest first)
    def _ch_key(c):
        try:
            return float(c["number"])
        except Exception:
            return 0.0

    chapters.sort(key=_ch_key, reverse=True)

    if not chapters and not synopsis and title == slug.replace("-", " ").title():
        # might be soft 404 page
        if "tidak ditemukan" in html.lower() or len(html) < 5000:
            raise HTTPException(404, "Series not found")

    return {
        "ok": True,
        "id": f"{type_}/{slug}",
        "type": type_,
        "slug": slug,
        "title": re.sub(r"\s*Bahasa Indonesia\s*$", "", title, flags=re.I).strip(),
        "cover": cover,
        "synopsis": synopsis,
        "genres": genres,
        "status": status,
        "author": author,
        "chapters_count": len(chapters),
        "chapters": chapters,
        "url": url,
        "source": "wurmz",
    }


@app.get("/chapter/{type_}/{slug}/{num}")
async def chapter_images(type_: str, slug: str, num: str):
    type_ = type_.lower().strip()
    slug = slug.lower().strip()
    num = num.strip()
    if type_ not in ("manga", "manhwa", "manhua"):
        raise HTTPException(400, "type must be manga|manhwa|manhua")
    url = f"{BASE}/detail/{type_}/{slug}/chapter/{num}"
    r = await _get(url)
    html = r.text

    images: list[str] = []
    seen = set()

    def add(u: str):
        u = _clean_img(u)
        if not u:
            return
        # strip trailing escapes
        u = u.rstrip("\\").rstrip('"').rstrip("'")
        key = re.sub(r"[?&]rt=\d+", "", u)
        if key in seen:
            return
        seen.add(key)
        images.append(u)

    # Prefer Voratoon CDN (actual pages)
    for u in re.findall(
        r"https?://cdn\.voratoon\.com[^\s\"'<>\\]+",
        html,
        re.I,
    ):
        add(u)

    # Other http images as fallback
    if len(images) < 3:
        for u in re.findall(r"https?://[^\s\"'<>\\]+\.(?:jpg|jpeg|png|webp)", html, re.I):
            low = u.lower()
            if "cover" in low or "wurmz.net/covers" in low:
                continue
            add(u)

    if HAS_BS4 and len(images) < 3:
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            for attr in ("src", "data-src", "data-lazy-src", "data-original"):
                if img.get(attr):
                    add(img.get(attr))
            srcset = img.get("srcset") or ""
            for part in srcset.split(","):
                add(part.strip().split(" ")[0])

    # filter tiny / ad leftovers
    images = [
        u
        for u in images
        if not re.search(r"/s(2[0-9]|[1-9]\d?)[-/]", u)  # tiny blogger sizes
        and "emoji" not in u.lower()
    ]

    if not images:
        raise HTTPException(404, "Chapter images not found")

    return {
        "ok": True,
        "id": f"{type_}/{slug}/{num}",
        "type": type_,
        "slug": slug,
        "number": num,
        "images_count": len(images),
        "images": images,
        "url": url,
        "source": "wurmz",
    }


# Vercel / serverless
handler = app
