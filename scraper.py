"""
scraper.py — Lust Arcade Auto-Scraper
Scrapes game listings from fapnation.com and saves to games.json
Run manually:  python scraper.py
Auto-run:      GitHub Actions every 2 hours (see .github/workflows/scrape.yml)
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
import os
import sys
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASE_URL      = "https://fapnation.com"
GAMES_URL     = f"{BASE_URL}/games/"        # main games listing page
OUTPUT_FILE   = "games.json"
MAX_PAGES     = 10                           # how many listing pages to scrape
DELAY_SECONDS = 2                            # polite delay between requests
HEADERS       = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL,
}

# ── HELPERS ───────────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update(HEADERS)

def get_soup(url, retries=3):
    """Fetch URL and return BeautifulSoup object."""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"  ⚠ Attempt {attempt+1} failed for {url}: {e}")
            time.sleep(3)
    return None

def slugify(text):
    """Convert title to URL-safe ID."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text

def clean_text(el):
    """Get clean text from a BeautifulSoup element."""
    if el is None:
        return ""
    return el.get_text(separator=" ", strip=True)

# ── SCRAPE GAME LISTING PAGE ──────────────────────────────────────────────────
def scrape_listing_page(url):
    """
    Scrape one page of game listings.
    Returns list of {url, title, cover} dicts.
    """
    print(f"  📄 Listing: {url}")
    soup = get_soup(url)
    if not soup:
        return []

    games = []

    # fapnation uses article cards — adjust selector if site changes
    # Common patterns to try (script tries each):
    card_selectors = [
        "article.post",
        ".game-card",
        ".entry-card",
        "article",
        ".post-item",
    ]

    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if cards:
            break

    for card in cards:
        try:
            # Title + link
            link_el = card.select_one("a[href]")
            title_el = card.select_one("h2, h3, .entry-title, .game-title")
            img_el   = card.select_one("img")

            if not link_el:
                continue

            href  = link_el.get("href", "")
            if not href.startswith("http"):
                href = BASE_URL.rstrip("/") + "/" + href.lstrip("/")

            title = clean_text(title_el) if title_el else clean_text(link_el)
            if not title:
                continue

            # Cover image
            cover = ""
            if img_el:
                cover = (img_el.get("data-src")
                      or img_el.get("data-lazy-src")
                      or img_el.get("src")
                      or "")

            games.append({"url": href, "title": title, "cover": cover})

        except Exception as e:
            print(f"    ⚠ Card parse error: {e}")
            continue

    print(f"    ✓ Found {len(games)} games")
    return games

# ── SCRAPE INDIVIDUAL GAME PAGE ───────────────────────────────────────────────
def scrape_game_detail(url, title, cover):
    """
    Scrape a single game detail page.
    Returns a game dict ready for games.json.
    """
    print(f"    🎮 Detail: {title[:50]}")
    soup = get_soup(url)
    if not soup:
        return None

    # ── Description ──────────────────────────────────────
    desc = ""
    for sel in [".entry-content p", ".game-description", ".synopsis", "article p"]:
        el = soup.select_one(sel)
        if el:
            desc = clean_text(el)
            break

    # ── Version ──────────────────────────────────────────
    version = ""
    for pattern in [r"[Vv]ersion[:\s]*([\w\.]+)", r"[Vv]([\d\.]+)"]:
        m = re.search(pattern, soup.get_text())
        if m:
            version = "v" + m.group(1).lstrip("vV")
            break

    # ── Developer ────────────────────────────────────────
    developer = ""
    for sel in [".developer a", ".author a", '[class*="developer"]', '[class*="author"]']:
        el = soup.select_one(sel)
        if el:
            developer = clean_text(el)
            break

    # ── Tags ─────────────────────────────────────────────
    tags = []
    for sel in [".tags a", ".tag a", '[class*="tag"] a', "a[rel='tag']", ".genre a"]:
        tag_els = soup.select(sel)
        if tag_els:
            tags = [clean_text(t) for t in tag_els if clean_text(t)]
            break

    # ── Screenshots ───────────────────────────────────────
    screenshots = []
    for sel in [".gallery img", ".screenshots img", ".wp-block-image img", ".entry-content img"]:
        imgs = soup.select(sel)
        for img in imgs:
            src = (img.get("data-src") or img.get("data-lazy-src") or img.get("src") or "")
            if src and src not in screenshots and not src.endswith((".gif",)):
                screenshots.append(src)
        if screenshots:
            break

    # Cover fallback to first screenshot
    final_cover = cover or (screenshots[0] if screenshots else "")

    # ── Download Links ────────────────────────────────────
    dl_links = []
    dl_hosts = ["mega", "mediafire", "fileknot", "pixeldrain", "workupload",
                "gofile", "mixdrop", "anonfiles", "send", "wetransfer", "drive.google"]

    for a in soup.select("a[href]"):
        href = a.get("href", "").lower()
        text = clean_text(a)
        for host in dl_hosts:
            if host in href:
                # Detect platform from link text
                platform = "Windows"
                t_lower = text.lower()
                if "linux" in t_lower:   platform = "Linux"
                elif "mac" in t_lower:   platform = "Mac"
                elif "android" in t_lower: platform = "Android"

                dl_links.append({
                    "host": host.capitalize().replace("Drive.google", "Google Drive"),
                    "url":  a.get("href"),
                    "platform": platform
                })
                break

    # ── Status ───────────────────────────────────────────
    status = "Ongoing"
    text_lower = soup.get_text().lower()
    if "completed" in text_lower or "final" in text_lower:
        status = "Completed"
    elif "abandoned" in text_lower:
        status = "Abandoned"
    elif "on hold" in text_lower:
        status = "On Hold"

    # ── Engine ───────────────────────────────────────────
    engine = "Others"
    engines = {"ren'py": "Ren'Py", "renpy": "Ren'Py", "unity": "Unity",
               "rpgm": "RPGM", "rpg maker": "RPGM", "unreal": "Unreal",
               "godot": "Godot", "html": "HTML"}
    for key, val in engines.items():
        if key in text_lower:
            engine = val
            break

    return {
        "id":           slugify(title),
        "title":        title,
        "version":      version or "Unknown",
        "developer":    developer or "Unknown",
        "engine":       engine,
        "censorship":   "Uncensored",
        "status":       status,
        "release_date": datetime.now().strftime("%-d %B, %Y"),
        "file_size":    "",
        "views":        "0",
        "rating":       0,
        "votes":        0,
        "cover":        final_cover,
        "screenshots":  screenshots[:8],
        "tags":         tags[:15],
        "description":  desc,
        "changelog":    "",
        "download_links": dl_links,
        "source_url":   url,
        "scraped_at":   datetime.utcnow().isoformat() + "Z",
    }

# ── FIND NEXT PAGE URL ────────────────────────────────────────────────────────
def get_next_page(soup, current_url):
    """Try to find the next pagination URL."""
    for sel in ["a.next", "a[rel='next']", ".nav-next a", ".pagination .next a"]:
        el = soup.select_one(sel)
        if el and el.get("href"):
            return el["href"]

    # Fallback: look for page number pattern
    m = re.search(r"/page/(\d+)", current_url)
    if m:
        next_n = int(m.group(1)) + 1
        return re.sub(r"/page/\d+", f"/page/{next_n}", current_url)
    else:
        return current_url.rstrip("/") + "/page/2/"

# ── LOAD EXISTING DATA (merge, don't overwrite) ───────────────────────────────
def load_existing():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return {g["id"]: g for g in json.load(f)}
        except Exception:
            pass
    return {}

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(f"  Lust Arcade Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    existing = load_existing()
    print(f"  Existing games in DB: {len(existing)}")

    new_count = 0
    url = GAMES_URL

    for page_num in range(1, MAX_PAGES + 1):
        print(f"\n[Page {page_num}]")
        soup = get_soup(url)
        if not soup:
            break

        listings = scrape_listing_page(url)
        if not listings:
            print("  No games found on this page. Stopping.")
            break

        for item in listings:
            game_id = slugify(item["title"])

            # Skip if already scraped
            if game_id in existing:
                print(f"    ⏭ Skip (exists): {item['title'][:40]}")
                continue

            time.sleep(DELAY_SECONDS)
            detail = scrape_game_detail(item["url"], item["title"], item["cover"])

            if detail:
                existing[game_id] = detail
                new_count += 1
                print(f"    ✅ Added: {item['title'][:40]}")

        # Next page
        next_url = get_next_page(soup, url)
        if next_url == url or not next_url:
            print("\n  No more pages.")
            break
        url = next_url
        time.sleep(DELAY_SECONDS)

    # ── SAVE ──────────────────────────────────────────────
    games_list = sorted(
        existing.values(),
        key=lambda g: g.get("scraped_at", ""),
        reverse=True
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(games_list, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"  ✅ Done! {new_count} new games added. Total: {len(games_list)}")
    print(f"  💾 Saved to {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
