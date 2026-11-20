import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

BASE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(BASE, "corpus.json")
OUT = os.path.join(BASE, "corpus_cleaned.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

DROP_TAGS = ["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe", "header"]


def log(msg):
    print(msg, flush=True)


def dedupe_consecutive_lines(text):
    lines = []
    for line in text.split("\n"):
        key = re.sub(r"\W+", "", line).lower()
        if lines and key and key == re.sub(r"\W+", "", lines[-1]).lower():
            continue
        lines.append(line)
    return "\n".join(lines)


def clean_jina(text):
    def image(match):
        alt = re.sub(r"^Image\s*\d+\s*:\s*", "", match.group(1), flags=re.I).strip()
        if not alt or re.search(r"\.(webp|png|jpe?g|svg|gif)(\?|$)", alt, re.I):
            return " "
        return "\n" + alt + "\n"

    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", image, text)
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)",
                  lambda m: m.group(1).strip() or " ", text)
    text = re.sub(r"\[\s*\]\([^)]*\)", " ", text)
    text = re.sub(r"tw_document_href=\S+", " ", text)
    text = re.sub(r"gdpr_consent=\S+", " ", text)
    text = re.sub(r"\bord=\d+", " ", text)
    text = re.sub(r"%[0-9A-Fa-f]{2}", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"#{1,6}\s*We value our privacy.*?ACCEPT", " ", text, flags=re.S | re.I)
    text = re.sub(r"#{1,6}\s*Register Your Interest\s+Full Name.*?(?:offers\.|\Z)", " ", text, flags=re.S | re.I)
    text = re.sub(r"Register Your Interest\s+Full Name[^.]{0,200}\.", " ", text, flags=re.I)
    text = re.sub(r"Darglobal Register Interest\s*\+1\s*[\d\s]+\s*English\|العربية", " ", text, flags=re.I)
    text = re.sub(r"#{2,}\s*Luxury Real Estate Collections.*?All rights reserved\.", " ", text, flags=re.S | re.I)
    text = re.sub(r"(?m)^\s*Image\s+\d+\s*$", " ", text, flags=re.I)
    text = re.sub(r"#{2,}\s*FOLLOW US ON.*?(?=©|\Z)", " ", text, flags=re.S | re.I)
    text = re.sub(r"Privacy PolicyTerms of UseCookie Policy.*?(?=©|\Z)", " ", text, flags=re.S | re.I)
    text = re.sub(r"[^.]*\b(?:cookie|privacy policy)\b[^.]*\.", " ", text, flags=re.I)
    text = re.sub(r"\s*(#{1,6})\s*", lambda m: "\n\n" + m.group(1) + " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
    return dedupe_consecutive_lines(text).strip()


def clean_pdf(text):
    start = re.search(r"\bAt a glance\b", text, re.I)
    end = re.search(r"Notes to the Company Financial Statements", text, re.I)
    if start and end and end.start() > start.start():
        text = text[:start.start()] + " " + text[end.end():]

    for pattern in [
        r"DARGLOBAL\.CO\.UK\s*ANNUAL REPORT & ACCOUNTS 2025\s*LIVE ALL IN",
        r"DAR GLOBAL PLC ANNUAL REPORT & ACCOUNTS 2025",
        r"\bANNUAL REPORT & ACCOUNTS 2025\b",
        r"\bTABLE OF CONTENTS\b",
        r"\bSTRATEGIC REPORT\b",
        r"\bGOVERNANCE REPORT\b",
        r"\bFINANCIAL STATEMENTS\b",
        r"\bLIVE ALL IN\b",
    ]:
        text = re.sub(pattern, " ", text, flags=re.I)

    text = re.sub(r"(?<!\w)\d{2}\.\s+(?=[A-Z])", " ", text)
    text = re.sub(r"^\d{1,2}\s+\d{1,2}\s+", "", text)
    text = re.sub(r"\b\d{2}\.\s*\d{2}\.\s*\d{1,2}\s+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def semantic_scrape(url):
    response = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers=HEADERS, timeout=45)
            response.raise_for_status()
            break
        except Exception:
            if attempt == 2:
                raise
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(DROP_TAGS):
        tag.decompose()
    body = soup.body or soup
    text = md(str(body), heading_style="ATX", strip=["a"])
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def dedupe_lines(text):
    seen = set()
    lines = []
    for line in text.split("\n"):
        key = re.sub(r"\W+", "", line).lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        lines.append(line)
    return "\n".join(lines)


def clean_wasalt(text, record_type):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\(([^)]*)\)", lambda m: m.group(1).strip() or " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"Map view", " ", text, flags=re.I)
    text = re.sub(r"Post Property", " ", text, flags=re.I)
    text = re.sub(r"Register Now", " ", text, flags=re.I)

    noise = [
        r"\bGet Matched\b", r"\bView all\b", r"\bDownload Wasalt\b", r"\bRegister Now\b",
        r"WhatsApp", r"Call Now", r"Click to go to URL", r"See more",
        r"people viewed this property", r"\bExplore Projects\b",
        r"for\s+(?:sale|rent)\s+in\b",
        r"^\s*[\*\-]\s+(?:Home|Saudi Arabia|Jeddah|Riyadh|Makkah|Madinah|Dammam|Khobar)\s*$",
        r"^\s*Call\s*$",
        r"^#{3,}\s+(?:Properties|Villas|Apartments|Lands|Buildings|Rest houses|Floors?)\s+for\s+(?:Sale|Rent)\s*$",
        r"^\s*[\*\-]\s+(?:Buy|Rent|Projects|Daily Rentals|BarterNew|City|District|Property type|Search|View commercial properties only)\s*$",
    ]
    filter_labels = {
        "buy", "rent", "projects", "daily rentals", "barternew", "city", "district",
        "property type", "search", "view commercial properties only",
        "explore international luxury properties",
    }
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.lower() in filter_labels:
            continue
        if any(re.search(p, stripped, re.I) for p in noise):
            continue
        lines.append(line)
    text = dedupe_lines("\n".join(lines))
    text = dedupe_consecutive_lines(text)

    if record_type == "property_listing":
        kept = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.count("Apartment") >= 3 and re.search(r"\b(?:bedroom|SQM)\b", stripped, re.I):
                continue
            kept.append(line)
        text = "\n".join(kept)

    if record_type == "property_listing":
        parts = re.split(r"(?<=\.)\s+", text)
        seen = set()
        kept = []
        for part in parts:
            key = re.sub(r"\W+", "", part).lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            kept.append(part)
        text = " ".join(kept)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n+", "\n\n", text)
    return text.strip()


def main():
    records = json.load(open(RAW, encoding="utf-8"))
    log(f"raw records: {len(records)}")
    cleaned = []
    for i, record in enumerate(records, 1):
        result = dict(record)
        kind = record.get("record_type")
        try:
            if record["source"] == "DarGlobal" and kind == "website_page":
                result["text"] = clean_jina(record["text"])
            elif kind == "pdf_report":
                result["text"] = clean_pdf(record["text"])
            elif record["source"] == "Wasalt":
                fresh = semantic_scrape(record["url"])
                result["text"] = clean_wasalt(fresh, kind)
            else:
                result["text"] = clean_jina(record["text"])
            log(f"[{i}/{len(records)}] {record['source']:9s} {kind:16s} {len(record['text']):6d} -> {len(result['text']):6d}  {record['title'][:45]}")
        except Exception as exc:
            log(f"[{i}/{len(records)}] ERROR {record['url']}: {type(exc).__name__}: {exc}")
            if record["source"] == "Wasalt":
                result["text"] = clean_wasalt(record["text"], kind)
            elif kind == "pdf_report":
                result["text"] = clean_pdf(record["text"])
            else:
                result["text"] = clean_jina(record["text"])
        result["text"] = re.sub(r"https?://\S+", " ", result["text"])
        result["text"] = re.sub(r"#{1,6}\s*We value our privacy.*?ACCEPT", " ", result["text"], flags=re.S | re.I)
        result["text"] = re.sub(r"you consent to our use of cookies\..*?ACCEPT", " ", result["text"], flags=re.S | re.I)
        result["text"] = re.sub(r"FIND OUT MOREACCEPT", " ", result["text"], flags=re.I)
        result["text"] = re.sub(r"[^.]*\buse of cookies\b[^.]*\.?", " ", result["text"], flags=re.I)
        result["text"] = re.sub(r"\bImage\s+\d+\b", " ", result["text"], flags=re.I)
        result["text"] = re.sub(r"\n{3,}", "\n\n", result["text"]).strip()
        result["cleaned"] = True
        cleaned.append(result)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    log(f"DONE -> {OUT} ({len(cleaned)} records)")


if __name__ == "__main__":
    main()
