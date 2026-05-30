#!/usr/bin/env python3
import json
import os
import re
import smtplib
import ssl
from html import escape
from email.message import EmailMessage
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "index.html"
SITE_URL = os.getenv("SITE_URL") or "https://ziopeno.github.io/farmhannong-agro-weekly-db/"


def parse_database():
    html = INDEX_PATH.read_text(encoding="utf-8")
    marker = "const newsDatabase = "
    start = html.index(marker) + len(marker)
    end = html.index(";\n        let allDates", start)
    return json.loads(html[start:end])


def strip_markup(value):
    text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_recipients(value):
    return [item.strip() for item in re.split(r"[,;\n]+", value or "") if item.strip()]


def build_messages(latest, cards):
    plain_lines = [
        f"Farmhannong Agro Weekly - {latest}",
        "",
        f"사이트: {SITE_URL}",
        "",
    ]
    html_lines = [
        "<h2>Farmhannong Agro Weekly</h2>",
        f"<p><strong>최근 업데이트:</strong> {latest}</p>",
        f'<p><a href="{SITE_URL}">사이트에서 전체 카드뉴스 보기</a></p>',
        "<hr>",
    ]

    for index, card in enumerate(cards, start=1):
        title = re.sub(r"^\d+\.\s*", "", card.get("title", ""))
        body_text = strip_markup(card.get("body", ""))
        source = card.get("source", "")
        country = card.get("country", "")
        company = card.get("company", "")
        escaped_title = escape(title)
        escaped_source = escape(source)
        escaped_country = escape(country)
        escaped_company = escape(company)
        escaped_body = escape(body_text).replace("\n", "<br>")

        plain_lines.extend(
            [
                f"{index}. {title}",
                f"국가: {country} / 기업: {company} / 출처: {source}",
                body_text,
                "",
            ]
        )
        html_lines.extend(
            [
                f"<h3>{index}. {escaped_title}</h3>",
                f"<p><strong>국가:</strong> {escaped_country} / <strong>기업:</strong> {escaped_company} / <strong>출처:</strong> {escaped_source}</p>",
                f"<p>{escaped_body}</p>",
            ]
        )

    return "\n".join(plain_lines), "\n".join(html_lines)


def main():
    recipients = split_recipients(os.getenv("SUMMARY_EMAIL_RECIPIENTS", ""))
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user

    if not recipients:
        print("SUMMARY_EMAIL_RECIPIENTS is empty; skipped weekly summary email.")
        return
    missing = [name for name, value in {
        "SMTP_HOST": smtp_host,
        "SMTP_USERNAME": smtp_user,
        "SMTP_PASSWORD": smtp_password,
        "SMTP_FROM or SMTP_USERNAME": smtp_from,
    }.items() if not value]
    if missing:
        print(f"SMTP is not fully configured; skipped weekly summary email. Missing: {', '.join(missing)}")
        return

    db = parse_database()
    latest = sorted(db.keys(), reverse=True)[0]
    cards = db[latest]
    plain_body, html_body = build_messages(latest, cards)

    message = EmailMessage()
    message["Subject"] = f"Farmhannong Agro Weekly 요약 - {latest}"
    message["From"] = smtp_from
    message["To"] = ", ".join(recipients)
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30) as server:
            server.login(smtp_user, smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_password)
            server.send_message(message)

    print(f"Sent weekly summary email to {len(recipients)} recipient(s).")


if __name__ == "__main__":
    main()
