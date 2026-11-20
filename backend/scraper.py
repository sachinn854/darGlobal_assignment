import io
import os
import sys
import re
import time
import gzip
import random
import json
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

BASE = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(BASE, "corpus.json")
FAILED_PATH = os.path.join(BASE, "failed_urls.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

DAR_SITEMAP = "https://darglobal.co.uk/sitemap.xml"
WASALT_SITEMAPS = [
    "https://cdn.wasalt.sa/sitemap/static_sitemap_en_sa.xml.gz",
    "https://cdn.wasalt.sa/sitemap/category_sitemap_en_sa.xml.gz",
    "https://cdn.wasalt.sa/sitemap/product_sitemap_en_sa.xml.gz",
]

DAR_SEEDS = [
    "https://darglobal.co.uk/investor",
    "https://darglobal.co.uk/aida-360",
    "https://darglobal.co.uk/faq",
]
WASALT_SEEDS = [
    "https://wasalt.sa/en",
    "https://wasalt.sa/en/corporate",
    "https://wasalt.sa/en/s/masterplan",
    "https://wasalt.sa/en/s/wasalt-business",
]

PDF_SOURCES = [
    {
        "url": "https://cdn.darglobal.co.uk/DG_Financial_Report_2025_979998177b.pdf",
        "title": "DarGlobal Annual Report & Accounts 2025",
    },
    {
        "url": "https://cdn.darglobal.co.uk/2_RNS_Announcement_Dar_Global_FY_25_Full_Statement_of_Results_10032026_v5_Clean_002_SIGNED_5e321d5bc0.pdf",
        "title": "DarGlobal FY25 Full Statement of Results",
    },
]

MAX_PAGES = {"DarGlobal": 40, "Wasalt": 30}
MAX_ATTEMPTS = 2
JINA_BASE = "https://r.jina.ai/"
WASALT_LISTINGS = 26
MIN_TEXT_LENGTH = 200
DELAY_RANGE = (1.5, 3.0)


def log(msg):
    print(msg, flush=True)


def polite_delay():
    time.sleep(random.uniform(*DELAY_RANGE))


def get_sitemap_urls(session, url):
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            log(f"  sitemap {url} -> status {r.status_code}")
            return []
        raw = r.content
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        body = raw.decode("utf-8", errors="ignore")
        return [u.strip() for u in re.findall(r"<loc>(.*?)</loc>", body)]
    except Exception as e:
        log(f"  sitemap {url} -> ERROR {type(e).__name__}: {e}")
        return []


def select_dar_urls(all_urls):
    keys = (
        "/press/", "/blog/", "/insights/", "/partners/",
        "/investor", "/about", "/faq", "/why-invest",
        "/commercial", "/hospitality", "/tokenization",
        "/one-of-one/", "/rayana/", "/amaya/", "/trump-plaza/",
        "/aida", "/project",
    )
    picked = []
    for u in DAR_SEEDS:
        if u not in picked:
            picked.append(u)
    for u in all_urls:
        if len(picked) >= MAX_PAGES["DarGlobal"]:
            break
        path = urlparse(u).path.lower()
        if "?" in u or "#" in u:
            continue
        if any(k in path for k in keys) and u not in picked:
            picked.append(u)
    return picked[: MAX_PAGES["DarGlobal"]]


def select_wasalt_urls(all_urls):
    picked = []
    for u in WASALT_SEEDS:
        if u not in picked:
            picked.append(u)
    listings = []
    for u in all_urls:
        path = urlparse(u).path.lower()
        if "?" in u or "#" in u:
            continue
        if "/en/" not in path and path != "/en":
            continue
        if "/en/property/" in path:
            if u not in listings:
                listings.append(u)
    for u in listings[:WASALT_LISTINGS]:
        if u not in picked:
            picked.append(u)
    return picked[: MAX_PAGES["Wasalt"]]


def is_blocked(html):
    low = html.lower()
    return "incapsula" in low or "request unsuccessful" in low or len(html) < 2000


def clean_html(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(" ", strip=True) or title
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe"]):
        tag.decompose()
    body = soup.body or soup
    text = body.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


DAR_BRANDS = [
    "Trump Organization", "Trump International", "Aston Martin", "Automobili Lamborghini",
    "Lamborghini", "ELIE SAAB", "Marriott Residences", "Missoni", "Mouawad",
    "Fendi Casa", "Fendi", "Pagani", "Paramount", "W Hotels", "Nickelodeon",
    "Dolce & Gabbana", "Rothschild", "Marriott",
]
DAR_COUNTRIES = [
    "United Kingdom", "UK", "Spain", "Greece", "Saudi Arabia", "United Arab Emirates",
    "UAE", "Oman", "United States", "Qatar", "Maldives", "Bosnia",
]
DAR_PROJECTS = [
    "AIDA", "Trump Tower Jeddah", "Trump Plaza", "DG1", "The Astera", "Tierra Viva",
    "Marea", "Urban Oasis", "Les Vagues", "Neptune", "The Mulliner", "W Residences",
    "Trump International Hotel", "D-Villas", "Da Vinci Tower", "Rayana", "Amaya",
    "One of One", "Fendi Casa Azure", "Great Escape",
]
WASALT_CITIES = [
    "Riyadh", "Jeddah", "Makkah", "Madinah", "Dammam", "Al Khobar", "Khobar",
    "Taif", "Abha", "Buraidah", "Khamis Mushayt",
]


def find_all(text, options):
    found = []
    low = text.lower()
    for option in options:
        if option.lower() in low and option.lower() not in [f.lower() for f in found]:
            found.append(option)
    return found


def enrich_record(rec):
    text = rec["text"]
    title = rec["title"] or ""
    url = rec["url"]
    low = text.lower()
    if rec["source"] == "Wasalt":
        if "/en/property/" in url:
            rec["record_type"] = "property_listing"
            m = re.search(r"\b(Apartment|Villa|Land|Commercial|Office|Shop|Townhouse|Duplex)\b", title, re.I)
            rec["property_type"] = m.group(1) if m else ""
            rec["purpose"] = "rent" if "/rent/" in url else "sale"
            m = re.search(r"([\d,.]+)\s*(?:SQM|sqm)", text, re.I)
            rec["area_sqm"] = m.group(1).replace(",", "").strip() if m else ""
            m = re.search(r"(\d+)\s*bedrooms?", text, re.I)
            rec["bedrooms"] = int(m.group(1)) if m else None
            m = re.search(r"Price:\s*([\d,]+)\s*SAR", text, re.I) or re.search(r"([\d,]+)\s*SAR", text, re.I)
            rec["price_sar"] = int(m.group(1).replace(",", "")) if m else None
            idx = text.find(title)
            segment = text[idx:idx + 600] if idx >= 0 else text[:600]
            cities = find_all(segment, WASALT_CITIES)
            rec["city"] = cities[-1] if cities else ""
            m = re.search(r"Building year:\s*(\d{4})", text, re.I)
            rec["building_year"] = int(m.group(1)) if m else None
            m = re.search(r"Property usage\s+(\w+)", text, re.I)
            rec["property_usage"] = m.group(1) if m else ""
            m = re.search(r"REGA Ad License No\s+(\d+)", text, re.I)
            rec["rega_ad_license"] = m.group(1) if m else ""
            m = re.search(r"Ref no\.\s*(\d+)", text, re.I)
            rec["ref_no"] = m.group(1) if m else ""
            m = re.search(r"Last updated:\s*(\d+\s+days?\s+ago)", text, re.I)
            rec["last_updated"] = m.group(1) if m else ""
        else:
            rec["record_type"] = "company_info"
            rec["rega_licensed"] = "REGA" in text
            rec["license_number"] = "1200016591" if "1200016591" in text else ""
            rec["services"] = find_all(text, [
                "Wasalt Search", "Wasalt Auctions", "Wasalt Projects",
                "Wasalt Matchmaker", "Masterplan", "Daily Rentals",
            ])
    else:
        rec["record_type"] = "pdf_report" if url.lower().endswith(".pdf") else "website_page"
        brands = find_all(text, DAR_BRANDS)
        rec["brand_partners"] = [
            b for b in brands
            if not any(b.lower() != o.lower() and b.lower() in o.lower() for o in brands)
        ]
        rec["countries"] = find_all(text, DAR_COUNTRIES)
        rec["project_names"] = find_all(text, DAR_PROJECTS)
        rec["financial_highlights"] = list(dict.fromkeys(re.findall(
            r"(?:SAR|AED|USD)\s*[\d,.]+\s*(?:billion|million|mln)", text, re.I)))[:12]
        rec["lse_listed"] = "london stock exchange" in low
        m = re.search(r"(\d+)\s*cities", text, re.I)
        rec["cities_mentioned_count"] = int(m.group(1)) if m else None
        m = re.search(r"(\d+)\s*countries", text, re.I)
        rec["countries_mentioned_count"] = int(m.group(1)) if m else None
    return rec


def fetch_html(session, url, failures):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = session.get(url, timeout=30, allow_redirects=True)
            html = r.text
            if r.status_code != 200:
                reason = f"status {r.status_code}"
            elif is_blocked(html):
                reason = "bot-block or empty page"
            else:
                return html, None
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
        if attempt < MAX_ATTEMPTS:
            time.sleep(2 * attempt)
    failures.append({"url": url, "reason": reason, "attempts": MAX_ATTEMPTS})
    log(f"    SKIP ({reason}): {url}")
    return None, reason


def fetch_jina(session, url):
    try:
        r = session.get(JINA_BASE + url, timeout=60)
        if r.status_code != 200:
            return None
        raw = re.sub(r"\s+", " ", r.text).strip()
        if len(raw) < MIN_TEXT_LENGTH:
            return None
        m = re.search(r"Title:\s*(.*?)\s*URL Source:", raw)
        title = m.group(1).strip() if m else ""
        text = raw.split("Markdown Content:", 1)[1].strip() if "Markdown Content:" in raw else raw
        if len(text) < MIN_TEXT_LENGTH:
            return None
        return title, text
    except Exception as e:
        log(f"    jina ERROR {type(e).__name__}: {e}")
        return None


def scrape_pages(session, source, urls, failures, use_jina=False):
    records = []
    seen = set()
    log(f"\n[{source}] {len(urls)} pages")
    for i, url in enumerate(urls, 1):
        title = text = None
        if use_jina:
            result = fetch_jina(session, url)
            polite_delay()
            if result:
                title, text = result
                log(f"    jina OK: {url}")
        else:
            html, _ = fetch_html(session, url, failures)
            polite_delay()
            if html:
                title, text = clean_html(html)
        if not text or len(text) < MIN_TEXT_LENGTH:
            failures.append({"url": url, "reason": "no usable text", "attempts": 1})
            log(f"    SKIP (no usable text): {url}")
            continue
        key = re.sub(r"\W+", "", text[:400]).lower()
        if key in seen:
            log(f"    SKIP (duplicate): {url}")
            continue
        seen.add(key)
        records.append(enrich_record({"source": source, "url": url, "title": title, "text": text}))
        log(f"  [{i}/{len(urls)}] OK  {len(text):6d} chars  {title[:60]}")
    return records


def scrape_pdfs(session, failures):
    records = []
    log(f"\n[PDF fallback] {len(PDF_SOURCES)} documents")
    if PdfReader is None:
        log("  pypdf not installed - skipped")
        return records
    for item in PDF_SOURCES:
        url = item["url"]
        try:
            r = session.get(url, timeout=60)
            if r.status_code != 200 or not r.content[:4] == b"%PDF":
                raise ValueError(f"not a PDF (status {r.status_code})")
            reader = PdfReader(io.BytesIO(r.content))
            parts = []
            for page in reader.pages[:45]:
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(t)
            text = re.sub(r"\s+", " ", " ".join(parts)).strip()
            if len(text) < MIN_TEXT_LENGTH:
                raise ValueError("extracted text too short")
            records.append(enrich_record({
                "source": "DarGlobal",
                "url": url,
                "title": item["title"],
                "text": text,
            }))
            log(f"  OK  {len(text)} chars  {item['title']}")
        except Exception as e:
            reason = f"PDF: {type(e).__name__}: {e}"
            failures.append({"url": url, "reason": reason, "attempts": 1})
            log(f"  SKIP ({reason})")
        polite_delay()
    return records


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    session = requests.Session()
    session.headers.update(HEADERS)
    failures = []
    all_records = []

    log("Fetching sitemaps...")
    dar_all = get_sitemap_urls(session, DAR_SITEMAP)
    wasalt_all = []
    for sm in WASALT_SITEMAPS:
        wasalt_all.extend(get_sitemap_urls(session, sm))
    log(f"DarGlobal sitemap URLs: {len(dar_all)}")
    log(f"Wasalt sitemap URLs: {len(wasalt_all)}")

    dar_records = scrape_pages(session, "DarGlobal", select_dar_urls(dar_all), failures, use_jina=True)
    all_records.extend(dar_records)
    write_json(CORPUS_PATH, all_records)

    wasalt_records = scrape_pages(session, "Wasalt", select_wasalt_urls(wasalt_all), failures)
    all_records.extend(wasalt_records)
    write_json(CORPUS_PATH, all_records)

    pdf_records = scrape_pdfs(session, failures)
    all_records.extend(pdf_records)
    write_json(CORPUS_PATH, all_records)
    write_json(FAILED_PATH, failures)

    counts = {}
    for rec in all_records:
        counts[rec["source"]] = counts.get(rec["source"], 0) + 1
    log("\n" + "=" * 60)
    log(f"DONE. records={len(all_records)}  by_source={counts}")
    log(f"failed/skipped={len(failures)}")
    log(f"corpus -> {CORPUS_PATH}")
    log(f"failures -> {FAILED_PATH}")


if __name__ == "__main__":
    main()
