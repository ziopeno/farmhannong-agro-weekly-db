#!/usr/bin/env python3
import argparse
import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape, unescape
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "index.html"
OUTPUT_DIR = REPO_ROOT / "weekly-email-output"
SITE_URL = os.getenv("SITE_URL") or "https://ziopeno.github.io/farmhannong-agro-weekly-db/"
GREETING = "금주의 Agro weekly를 공유드리오니 업무에 참고 부탁드립니다."


def parse_database():
    html = INDEX_PATH.read_text(encoding="utf-8")
    marker = "const newsDatabase = "
    start = html.index(marker) + len(marker)
    end = html.index(";\n        let allDates", start)
    return json.loads(html[start:end])


def strip_markup(value):
    text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def split_recipients(value):
    return [item.strip() for item in re.split(r"[,;\n]+", value or "") if item.strip()]


def card_title(card):
    return re.sub(r"^\d+\.\s*", "", strip_markup(card.get("title", "")))


def card_tag_label(tag):
    return {"reg": "등록", "dev": "개발", "sales": "시장"}.get(tag, "시장")


def card_tag_color(tag):
    return {"reg": "#27ae60", "dev": "#3498db", "sales": "#e67e22"}.get(tag, "#006600")


def latest_cards():
    db = parse_database()
    latest = sorted(db.keys(), reverse=True)[0]
    return latest, db[latest]


def pdf_font_names():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    for font_name in ("HYGothic-Medium", "HYSMyeongJo-Medium"):
        try:
            pdfmetrics.registerFont(UnicodeCIDFont(font_name))
        except Exception:
            pass
    return "HYGothic-Medium", "HYSMyeongJo-Medium"


def generate_weekly_pdf(latest, cards):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    OUTPUT_DIR.mkdir(exist_ok=True)
    pdf_path = OUTPUT_DIR / f"Farmhannong_Agro_Weekly_{latest}.pdf"
    font_name, serif_font = pdf_font_names()
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Farmhannong Agro Weekly {latest}",
    )
    title_style = ParagraphStyle(
        "WeeklyTitle",
        fontName=font_name,
        fontSize=18,
        leading=24,
        textColor=colors.HexColor("#006600"),
        spaceAfter=6,
        wordWrap="CJK",
    )
    intro_style = ParagraphStyle(
        "WeeklyIntro",
        fontName=font_name,
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#4a5568"),
        spaceAfter=10,
        wordWrap="CJK",
    )
    card_title_style = ParagraphStyle(
        "CardTitle",
        fontName=font_name,
        fontSize=11,
        leading=16,
        textColor=colors.HexColor("#1a202c"),
        spaceAfter=5,
        wordWrap="CJK",
    )
    meta_style = ParagraphStyle(
        "CardMeta",
        fontName=font_name,
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#718096"),
        spaceAfter=5,
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "CardBody",
        fontName=serif_font,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#2d3748"),
        wordWrap="CJK",
    )

    story = [
        Paragraph(f"Farmhannong Agro Weekly - {escape(latest)}", title_style),
        Paragraph(escape(GREETING), intro_style),
        Paragraph(f"전체 카드뉴스 {len(cards)}건 / 사이트: {escape(SITE_URL)}", intro_style),
    ]

    for index, card in enumerate(cards, start=1):
        title = card_title(card)
        body = strip_markup(card.get("body", ""))
        meta = " / ".join(
            item
            for item in [
                card_tag_label(card.get("tag")),
                f"국가: {strip_markup(card.get('country', ''))}",
                f"기업: {strip_markup(card.get('company', ''))}",
                f"출처: {strip_markup(card.get('source', ''))}",
            ]
            if item and not item.endswith(": ")
        )
        content = [
            Paragraph(f"{index}. {escape(title)}", card_title_style),
            Paragraph(escape(meta), meta_style),
            Paragraph(escape(body).replace("\n", "<br/>"), body_style),
        ]
        table = Table([[content]], colWidths=[doc.width])
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#cfd8e3")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.extend([table, Spacer(1, 7)])

    doc.build(story)
    return pdf_path


def load_image_font(size, bold=False):
    from PIL import ImageFont

    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/AppleGothic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def wrap_text(draw, text, font, max_width, max_lines=None):
    lines = []
    for raw_line in strip_markup(text).splitlines() or [""]:
        current = ""
        for char in raw_line:
            candidate = current + char
            if not current or text_width(draw, candidate, font) <= max_width:
                current = candidate
            else:
                lines.append(current.rstrip())
                current = char.lstrip()
                if max_lines and len(lines) >= max_lines:
                    return lines
        if current:
            lines.append(current.rstrip())
            if max_lines and len(lines) >= max_lines:
                return lines
    return lines


def draw_wrapped(draw, text, x, y, font, fill, max_width, line_height, max_lines=None):
    lines = wrap_text(draw, text, font, max_width, max_lines)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def generate_weekly_jpg(latest, cards):
    from PIL import Image, ImageDraw

    OUTPUT_DIR.mkdir(exist_ok=True)
    jpg_path = OUTPUT_DIR / f"Farmhannong_Agro_Weekly_{latest}.jpg"
    width = 1400
    margin = 56
    gap = 24
    header_h = 210
    card_w = (width - margin * 2 - gap) // 2
    card_h = 220
    rows = (len(cards) + 1) // 2
    height = header_h + rows * (card_h + gap) + margin

    image = Image.new("RGB", (width, height), "#f7f9fc")
    draw = ImageDraw.Draw(image)
    title_font = load_image_font(44, bold=True)
    subtitle_font = load_image_font(24, bold=False)
    card_title_font = load_image_font(22, bold=True)
    meta_font = load_image_font(16, bold=True)
    body_font = load_image_font(17, bold=False)

    draw.rectangle((0, 0, width, header_h), fill="#ffffff")
    draw.text((margin, 38), "Farmhannong Agro Weekly", font=title_font, fill="#006600")
    draw.text((margin, 96), latest, font=subtitle_font, fill="#2d3748")
    draw.text((margin, 136), GREETING, font=subtitle_font, fill="#4a5568")

    for index, card in enumerate(cards, start=1):
        row = (index - 1) // 2
        col = (index - 1) % 2
        x = margin + col * (card_w + gap)
        y = header_h + row * (card_h + gap)
        tag_color = card_tag_color(card.get("tag"))
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=12, fill="#ffffff", outline="#d8e1ec", width=2)
        draw.rounded_rectangle((x + 18, y + 16, x + 82, y + 44), radius=6, fill=tag_color)
        draw.text((x + 30, y + 19), card_tag_label(card.get("tag")), font=meta_font, fill="#ffffff")
        draw.text((x + 96, y + 20), f"{strip_markup(card.get('country', ''))} / {strip_markup(card.get('company', ''))}", font=meta_font, fill="#718096")

        title_y = draw_wrapped(
            draw,
            f"{index}. {card_title(card)}",
            x + 18,
            y + 58,
            card_title_font,
            "#1a202c",
            card_w - 36,
            30,
            max_lines=2,
        )
        body_y = max(title_y + 8, y + 122)
        draw_wrapped(
            draw,
            strip_markup(card.get("body", "")),
            x + 18,
            body_y,
            body_font,
            "#2d3748",
            card_w - 36,
            25,
            max_lines=3,
        )

    image.save(jpg_path, "JPEG", quality=90, optimize=True)
    return jpg_path


def generate_weekly_assets(latest, cards):
    return generate_weekly_pdf(latest, cards), generate_weekly_jpg(latest, cards)


def build_messages(latest, cards, image_cid):
    plain_lines = [
        GREETING,
        "",
        f"Farmhannong Agro Weekly - {latest}",
        f"사이트: {SITE_URL}",
        "",
    ]
    html_lines = [
        f"<p>{escape(GREETING)}</p>",
        f'<p><img src="cid:{image_cid}" alt="Farmhannong Agro Weekly {escape(latest)} 요약 모음" style="width:100%;max-width:920px;border:1px solid #d8e1ec;border-radius:10px;"></p>',
        f'<p><a href="{escape(SITE_URL)}">사이트에서 전체 카드뉴스 보기</a></p>',
        "<hr>",
    ]

    for index, card in enumerate(cards, start=1):
        title = card_title(card)
        body_text = strip_markup(card.get("body", ""))
        source = strip_markup(card.get("source", ""))
        country = strip_markup(card.get("country", ""))
        company = strip_markup(card.get("company", ""))

        plain_lines.extend(
            [
                f"{index}. {title}",
                f"국가: {country} / 기업: {company} / 출처: {source}",
                body_text,
                "",
            ]
        )

    return "\n".join(plain_lines), "\n".join(html_lines)


def configured_smtp():
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT") or "587")
    smtp_user = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user
    return smtp_host, smtp_port, smtp_user, smtp_password, smtp_from


def main():
    parser = argparse.ArgumentParser(description="Send the latest Farmhannong Agro Weekly email summary.")
    parser.add_argument("--preview-only", action="store_true", help="Generate the weekly PDF/JPG without sending email.")
    args = parser.parse_args()

    latest, cards = latest_cards()
    if args.preview_only:
        pdf_path, jpg_path = generate_weekly_assets(latest, cards)
        print(json.dumps({"ok": True, "latest": latest, "pdf": str(pdf_path), "jpg": str(jpg_path)}, ensure_ascii=False, indent=2))
        return

    recipients = split_recipients(os.getenv("SUMMARY_EMAIL_RECIPIENTS", ""))
    if not recipients:
        print("SUMMARY_EMAIL_RECIPIENTS is empty; skipped weekly summary email.")
        return

    smtp_host, smtp_port, smtp_user, smtp_password, smtp_from = configured_smtp()
    missing = [
        name
        for name, value in {
            "SMTP_HOST": smtp_host,
            "SMTP_USERNAME": smtp_user,
            "SMTP_PASSWORD": smtp_password,
            "SMTP_FROM or SMTP_USERNAME": smtp_from,
        }.items()
        if not value
    ]
    if missing:
        print(f"SMTP is not fully configured; skipped weekly summary email. Missing: {', '.join(missing)}")
        return

    pdf_path, jpg_path = generate_weekly_assets(latest, cards)
    image_cid = make_msgid(domain="farmhannong-agro-weekly")
    plain_body, html_body = build_messages(latest, cards, image_cid[1:-1])

    message = EmailMessage()
    message["Subject"] = f"Ageo weekly 공유 ('{latest}')"
    message["From"] = smtp_from
    message["To"] = ", ".join(recipients)
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")

    html_part = message.get_payload()[-1]
    html_part.add_related(jpg_path.read_bytes(), maintype="image", subtype="jpeg", cid=image_cid)
    message.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=pdf_path.name)

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

    print(f"Sent weekly summary email to {len(recipients)} recipient(s) with PDF and JPG summary.")


if __name__ == "__main__":
    main()
