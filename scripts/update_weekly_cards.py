#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "index.html"
NEWS_MARKER = "const newsDatabase = "
NEWS_END_MARKER = ";\n        let allDates"
KST = ZoneInfo("Asia/Seoul")
REQUIRED_CARD_COUNT = 20
DEFAULT_MODEL = "gpt-4.1-mini"

SEARCH_QUERIES = [
    '("crop protection" OR pesticide OR herbicide OR fungicide OR insecticide) agriculture',
    '(agrochemical OR agrichemical OR "crop input") (market OR sales OR registration)',
    '(fertilizer OR urea OR ammonia OR potash) agriculture price',
    '(USDA OR FAO OR EPA OR EFSA OR APVMA OR PMRA) (pesticide OR crop OR fertilizer)',
    '(Bayer OR Syngenta OR BASF OR Corteva OR FMC OR UPL OR ADAMA) "crop protection"',
    '("biologicals" OR biopesticide OR biofertilizer OR "seed treatment") agriculture',
]

PREFERRED_DOMAINS = [
    "usda.gov",
    "fao.org",
    "europa.eu",
    "epa.gov",
    "apvma.gov.au",
    "canada.ca",
    "gov.br",
    "croplife.com",
    "agropages.com",
    "newaginternational.com",
    "agriculture.com",
    "business-standard.com",
    "economictimes.com",
    "reuters.com",
    "bloomberg.com",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect weekly agrochemical market news and update Farmhannong Agro Weekly cards."
    )
    parser.add_argument("--target-date", default=os.getenv("TARGET_DATE") or "", help="Monday date key to create, YYYY-MM-DD. Defaults to the current KST Monday.")
    parser.add_argument("--replace-existing", action="store_true", default=os.getenv("REPLACE_EXISTING", "").lower() == "true", help="Replace an existing target week.")
    parser.add_argument("--dry-run", action="store_true", help="Collect candidates and validate the pipeline without modifying index.html or calling OpenAI.")
    parser.add_argument("--max-candidates", type=int, default=int(os.getenv("MAX_CANDIDATES", "48")), help="Maximum candidate articles to send to OpenAI.")
    parser.add_argument("--max-article-fetches", type=int, default=int(os.getenv("MAX_ARTICLE_FETCHES", "32")), help="Maximum article pages to fetch for excerpts.")
    return parser.parse_args()


def kst_today():
    return datetime.now(KST).date()


def monday_for(value):
    return value - timedelta(days=value.weekday())


def parse_date_key(value):
    if not value:
        return monday_for(kst_today())
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"--target-date must be YYYY-MM-DD: {value}") from exc
    if parsed.weekday() != 0:
        raise SystemExit(f"--target-date must be a Monday date: {value}")
    return parsed


def week_window(target_monday):
    start = target_monday - timedelta(days=7)
    end = target_monday - timedelta(days=1)
    return start, end


def next_update_label(target_monday):
    return f"{target_monday + timedelta(days=7)} 09:00 (KST)"


def read_index():
    return INDEX_PATH.read_text(encoding="utf-8")


def extract_database(html):
    start = html.index(NEWS_MARKER) + len(NEWS_MARKER)
    end = html.index(NEWS_END_MARKER, start)
    return json.loads(html[start:end]), start, end


def write_database(html, db, data_start, data_end, target_key):
    encoded = json.dumps(db, ensure_ascii=False, separators=(",", ":"))
    updated = html[:data_start] + encoded + html[data_end:]
    updated = re.sub(r"최근 업데이트: [^<]+", f"최근 업데이트: {target_key}", updated)
    updated = re.sub(r"다음 업데이트 예정: [^<]+", f"다음 업데이트 예정: {next_update_label(date.fromisoformat(target_key))}", updated)
    INDEX_PATH.write_text(updated, encoding="utf-8")


def request_json(url, timeout=30):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "FarmhannongAgroWeeklyBot/1.0 (+https://ziopeno.github.io/farmhannong-agro-weekly-db/)"
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def request_text(url, timeout=12):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; FarmhannongAgroWeeklyBot/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        if "pdf" in content_type.lower() or url.lower().split("?")[0].endswith(".pdf"):
            return ""
        raw = response.read(1_000_000)
    return raw.decode("utf-8", errors="replace")


def gdelt_datetime(value, end=False):
    suffix = "235959" if end else "000000"
    return value.strftime("%Y%m%d") + suffix


def collect_from_gdelt(start_date, end_date):
    articles = []
    for query in SEARCH_QUERIES:
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": "75",
            "sort": "datedesc",
            "startdatetime": gdelt_datetime(start_date),
            "enddatetime": gdelt_datetime(end_date, end=True),
        }
        url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(params)
        try:
            payload = request_json(url)
        except Exception as exc:
            print(f"GDELT query skipped: {query} ({exc})", file=sys.stderr)
            continue

        for item in payload.get("articles", []):
            title = clean_text(item.get("title"))
            link = item.get("url") or ""
            if not title or not link:
                continue
            domain = clean_domain(item.get("domain") or urllib.parse.urlparse(link).netloc)
            articles.append(
                {
                    "title": title,
                    "url": link,
                    "source": domain or item.get("sourceCollectionIdentifier") or "Unknown source",
                    "published_date": clean_text(item.get("seendate")),
                    "domain": domain,
                    "source_country": clean_text(item.get("sourceCountry")),
                    "query": query,
                }
            )
        time.sleep(0.25)
    return articles


def collect_from_google_news(start_date, end_date):
    articles = []
    for query in SEARCH_QUERIES:
        dated_query = f'{query} after:{start_date.isoformat()} before:{(end_date + timedelta(days=1)).isoformat()}'
        params = {
            "q": dated_query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        }
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; FarmhannongAgroWeeklyBot/1.0)",
                    "Accept": "application/rss+xml,application/xml,text/xml",
                },
            )
            with urllib.request.urlopen(req, timeout=25) as response:
                root = ET.fromstring(response.read())
        except Exception as exc:
            print(f"Google News RSS query skipped: {query} ({exc})", file=sys.stderr)
            continue

        for item in root.findall(".//item"):
            full_title = clean_text(item.findtext("title"))
            link = clean_text(item.findtext("link"))
            pub_date = clean_text(item.findtext("pubDate"))
            source_el = item.find("source")
            source = clean_text(source_el.text if source_el is not None else "")
            title = full_title
            if source and full_title.endswith(f" - {source}"):
                title = full_title[: -len(source) - 3].strip()
            if not title or not link:
                continue
            articles.append(
                {
                    "title": title,
                    "url": link,
                    "source": source or "Google News",
                    "published_date": pub_date,
                    "domain": clean_domain(urllib.parse.urlparse(link).netloc),
                    "source_country": "",
                    "query": query,
                }
            )
        time.sleep(0.5)
    return articles


def clean_domain(value):
    return re.sub(r"^www\.", "", str(value or "").lower()).strip()


def clean_text(value):
    value = re.sub(r"<script[\s\S]*?</script>", " ", str(value or ""), flags=re.I)
    value = re.sub(r"<style[\s\S]*?</style>", " ", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"&nbsp;|&#160;", " ", value)
    value = re.sub(r"&amp;", "&", value)
    value = re.sub(r"&quot;", '"', value)
    value = re.sub(r"&#39;|&apos;", "'", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_key(value):
    return re.sub(r"\W+", "", str(value or "").lower())


def article_score(candidate):
    title = candidate.get("title", "").lower()
    domain = candidate.get("domain", "")
    score = 0
    score += 50 if any(domain.endswith(preferred) or preferred in domain for preferred in PREFERRED_DOMAINS) else 0
    score += 12 if any(term in title for term in ["pesticide", "herbicide", "fungicide", "insecticide", "crop protection", "agrochemical"]) else 0
    score += 8 if any(term in title for term in ["fertilizer", "urea", "seed", "biological", "registration", "approval", "price"]) else 0
    score += 4 if re.search(r"\d", title) else 0
    return score


def fetch_excerpt(url):
    try:
        text = request_text(url)
    except (urllib.error.URLError, TimeoutError, UnicodeDecodeError, ValueError):
        return ""
    if not text:
        return ""

    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", text, flags=re.I)
    title = clean_text(title_match.group(1)) if title_match else ""
    body = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    body = re.sub(r"<style[\s\S]*?</style>", " ", body, flags=re.I)
    paragraphs = re.findall(r"<p[^>]*>([\s\S]*?)</p>", body, flags=re.I)
    if paragraphs:
        content = " ".join(clean_text(p) for p in paragraphs)
    else:
        content = clean_text(body)
    content = re.sub(r"\s+", " ", content)
    if title and title not in content[:250]:
        content = f"{title}. {content}"
    return content[:1400]


def prepare_candidates(start_date, end_date, max_candidates, max_article_fetches):
    raw = collect_from_gdelt(start_date, end_date)
    raw.extend(collect_from_google_news(start_date, end_date))
    deduped = {}
    for candidate in raw:
        key = normalize_key(candidate.get("url")) or normalize_key(candidate.get("title"))
        if key and key not in deduped:
            deduped[key] = candidate

    ranked = sorted(deduped.values(), key=article_score, reverse=True)
    selected = ranked[:max_candidates]
    for index, candidate in enumerate(selected[:max_article_fetches]):
        candidate["excerpt"] = fetch_excerpt(candidate["url"])
        print(f"candidate {index + 1:02d}: {candidate['source']} | {candidate['title'][:80]}", file=sys.stderr)
        time.sleep(0.25)
    for candidate in selected[max_article_fetches:]:
        candidate["excerpt"] = ""
    return selected


def build_prompt(target_key, start_date, end_date, candidates):
    compact_candidates = []
    for index, candidate in enumerate(candidates, start=1):
        compact_candidates.append(
            {
                "id": index,
                "title": candidate.get("title", ""),
                "source": candidate.get("source", ""),
                "url": candidate.get("url", ""),
                "published_date": candidate.get("published_date", ""),
                "source_country": candidate.get("source_country", ""),
                "query": candidate.get("query", ""),
                "excerpt": candidate.get("excerpt", "")[:1000],
            }
        )

    return (
        "You create Farmhannong Agro Weekly Korean card news for overseas agrochemical sales.\n"
        f"Create exactly {REQUIRED_CARD_COUNT} cards for the Monday week key {target_key}.\n"
        f"Use only articles dated or seen from {start_date} to {end_date}. Use only the candidate articles below.\n"
        "Prioritize crop protection, agrochemical, fertilizer, seed, biologicals, regulation, crop price, supply/demand, and major agriculture company news.\n"
        "Each card must summarize what the source actually says, including concrete numbers, dates, crops, products, prices, registrations, volumes, or market impact when present. Do not merely describe the article topic.\n"
        "Do not fabricate facts that are not in the candidate title/excerpt. If detail is limited, write cautiously.\n"
        "Write all Korean-facing fields in Korean. Preserve original raw_title exactly from the source candidate title.\n"
        "body must be 3 concise Korean bullet lines joined by <br>, each starting with •.\n"
        "title must start with an item number like '1. ...'.\n"
        "tag must be one of reg, dev, sales.\n\n"
        "Candidate articles JSON:\n"
        + json.dumps(compact_candidates, ensure_ascii=False)
    )


CARD_SCHEMA = {
    "name": "weekly_cards",
    "strict": False,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "cards": {
                "type": "array",
                "minItems": REQUIRED_CARD_COUNT,
                "maxItems": REQUIRED_CARD_COUNT,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "tag": {"type": "string", "enum": ["reg", "dev", "sales"]},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "source": {"type": "string"},
                        "raw_title": {"type": "string"},
                        "raw_body": {"type": "string"},
                        "search_keywords": {"type": "string"},
                        "country": {"type": "string"},
                        "company": {"type": "string"},
                        "link": {"type": "string"},
                    },
                    "required": [
                        "tag",
                        "title",
                        "body",
                        "source",
                        "raw_title",
                        "raw_body",
                        "search_keywords",
                        "country",
                        "company",
                        "link",
                    ],
                },
            }
        },
        "required": ["cards"],
    },
}


def call_openai(prompt):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit(
            "OPENAI_API_KEY is missing. Add it as a GitHub repository secret before running the weekly automation."
        )

    model = os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a careful agricultural market intelligence editor. Output only valid JSON that matches the requested schema.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_schema", "json_schema": CARD_SCHEMA},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API request failed: HTTP {exc.code}\n{message}") from exc

    content = payload["choices"][0]["message"]["content"]
    return json.loads(content)["cards"]


def normalize_card(card, index):
    title = re.sub(r"^\d+\.\s*", "", clean_text(card.get("title")))
    body = card.get("body", "")
    body = re.sub(r"\n+", "<br>", body)
    body = re.sub(r"(?:<br>\s*){2,}", "<br>", body)
    body_lines = [line.strip() for line in re.split(r"<br\s*/?>", body) if line.strip()]
    body = "<br>".join(line if line.startswith("•") else f"• {line}" for line in body_lines[:3])

    return {
        "tag": card.get("tag") if card.get("tag") in {"reg", "dev", "sales"} else "sales",
        "title": f"{index + 1}. {title}",
        "body": body,
        "source": clean_text(card.get("source")),
        "raw_title": clean_text(card.get("raw_title")),
        "raw_body": clean_text(card.get("raw_body")),
        "search_keywords": clean_text(card.get("search_keywords")),
        "country": clean_text(card.get("country")) or "글로벌",
        "company": clean_text(card.get("company")) or "기타",
        "link": clean_text(card.get("link")),
    }


def update_index(target_key, cards, replace_existing):
    html = read_index()
    db, data_start, data_end = extract_database(html)
    if target_key in db and not replace_existing:
        print(f"{target_key} already exists; use --replace-existing to regenerate it.")
        return False

    normalized_cards = [normalize_card(card, index) for index, card in enumerate(cards)]
    if len(normalized_cards) != REQUIRED_CARD_COUNT:
        raise SystemExit(f"OpenAI returned {len(normalized_cards)} cards; expected {REQUIRED_CARD_COUNT}.")

    new_db = {target_key: normalized_cards}
    for key in sorted(db.keys(), reverse=True):
        if key != target_key:
            new_db[key] = db[key]
    write_database(html, new_db, data_start, data_end, target_key)
    return True


def main():
    args = parse_args()
    target_monday = parse_date_key(args.target_date)
    target_key = target_monday.isoformat()
    start_date, end_date = week_window(target_monday)

    html = read_index()
    db, _, _ = extract_database(html)
    if target_key in db and not args.replace_existing:
        print(json.dumps({"ok": True, "skipped": True, "reason": "target week already exists", "target": target_key}, ensure_ascii=False))
        return

    candidates = prepare_candidates(start_date, end_date, args.max_candidates, args.max_article_fetches)
    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "target": target_key, "period": [str(start_date), str(end_date)], "candidates": len(candidates)}, ensure_ascii=False, indent=2))
        return

    if len(candidates) < REQUIRED_CARD_COUNT:
        raise SystemExit(f"Only {len(candidates)} candidate articles found; expected at least {REQUIRED_CARD_COUNT}.")

    cards = call_openai(build_prompt(target_key, start_date, end_date, candidates))
    changed = update_index(target_key, cards, args.replace_existing)
    print(json.dumps({"ok": True, "target": target_key, "cards": len(cards), "changed": changed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
