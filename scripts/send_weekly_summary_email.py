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
INDEX_PATH = REPO_ROOT / "app.html"  # 평문 앱(git 미추적). 배포물은 payload.enc(암호문)
OUTPUT_DIR = REPO_ROOT / "weekly-email-output"
# 업로드 원본 리포트 PDF 보관 폴더(git 미추적). 메일 발송 시 해당 주차 PDF를 첨부(사이트엔 비제공).
REPORT_PDF_DIR = REPO_ROOT / "report-pdfs"


def source_report_pdfs(latest):
    week_dir = REPORT_PDF_DIR / str(latest)
    if not week_dir.is_dir():
        return []
    return sorted(p for p in week_dir.glob("*.pdf") if p.is_file())
SITE_URL = os.getenv("SITE_URL") or "https://ziopeno.github.io/farmhannong-agro-weekly-db/"
IMAGE_GREETING_TEMPLATE = "금주({latest})의 Agro weekly report를 송부드리오니 업무에 참고 바랍니다"
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"


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


def card_meta_fields(card):
    return [
        card_tag_label(card.get("tag")),
        f"국가: {strip_markup(card.get('country', ''))}",
        f"기업: {strip_markup(card.get('company', ''))}",
        f"출처: {strip_markup(card.get('source', ''))}",
    ]


def card_source_title(card):
    return strip_markup(card.get("raw_title", ""))


def image_greeting(latest):
    return IMAGE_GREETING_TEMPLATE.format(latest=latest)


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
    link_style = ParagraphStyle(
        "CardLink",
        fontName=font_name,
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#006600"),
        spaceBefore=4,
        wordWrap="CJK",
    )

    story = [
        Paragraph(f"Farmhannong Agro Weekly - {escape(latest)}", title_style),
        Paragraph(f"전체 카드뉴스 {len(cards)}건 / 사이트: {escape(SITE_URL)}", intro_style),
    ]

    for index, card in enumerate(cards, start=1):
        title = card_title(card)
        body = strip_markup(card.get("body", ""))
        meta = " / ".join(item for item in card_meta_fields(card) if item and not item.endswith(": "))
        source_title = card_source_title(card)
        source_link = strip_markup(card.get("link", ""))
        content = [
            Paragraph(f"{index}. {escape(title)}", card_title_style),
            Paragraph(escape(meta), meta_style),
            Paragraph(escape(body).replace("\n", "<br/>"), body_style),
        ]
        if source_title:
            content.append(Paragraph(f"원문 제목: {escape(source_title)}", link_style))
        if source_link:
            content.append(
                Paragraph(
                    f'출처 링크: <link href="{escape(source_link, quote=True)}" color="#006600">{escape(source_link)}</link>',
                    link_style,
                )
            )
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


def measure_wrapped_height(draw, text, font, max_width, line_height, max_lines=None):
    lines = wrap_text(draw, text, font, max_width, max_lines)
    return max(line_height, len(lines) * line_height), lines


def generate_weekly_jpg(latest, cards):
    from PIL import Image, ImageDraw

    OUTPUT_DIR.mkdir(exist_ok=True)
    jpg_path = OUTPUT_DIR / f"Farmhannong_Agro_Weekly_{latest}.jpg"
    width = 1300
    margin = 56
    gap = 24
    header_h = 210
    card_w = (width - margin * 2 - gap) // 2
    min_card_h = 220
    line_gap = 25
    meta_gap = 22
    inner_pad = 18
    measure_image = Image.new("RGB", (width, 200), "#f7f9fc")
    measure_draw = ImageDraw.Draw(measure_image)
    title_font = load_image_font(44, bold=True)
    subtitle_font = load_image_font(24, bold=False)
    card_title_font = load_image_font(22, bold=True)
    meta_font = load_image_font(16, bold=True)
    body_font = load_image_font(17, bold=False)
    link_font = load_image_font(15, bold=False)

    row_heights = []
    row_cards = []
    for start in range(0, len(cards), 2):
        pair = cards[start:start + 2]
        measured = []
        for index_offset, card in enumerate(pair, start=1):
            title_h, _ = measure_wrapped_height(
                measure_draw,
                f"{start + index_offset}. {card_title(card)}",
                card_title_font,
                card_w - 36,
                30,
            )
            body_h, _ = measure_wrapped_height(
                measure_draw,
                strip_markup(card.get("body", "")),
                body_font,
                card_w - 36,
                line_gap,
            )
            link_h = 0
            if strip_markup(card.get("link", "")):
                link_h, _ = measure_wrapped_height(
                    measure_draw,
                    f"출처 링크: {strip_markup(card.get('link', ''))}",
                    link_font,
                    card_w - 36,
                    20,
                )
            content_h = (
                inner_pad
                + 28
                + 18
                + title_h
                + 10
                + meta_gap
                + body_h
                + (10 + link_h if link_h else 0)
                + inner_pad
            )
            measured.append(max(min_card_h, content_h))
        row_cards.append(pair)
        row_heights.append(max(measured))

    height = header_h + margin
    for row_h in row_heights:
        height += row_h + gap

    image = Image.new("RGB", (width, height), "#f7f9fc")
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, width, header_h), fill="#ffffff")
    draw.text((margin, 38), "Farmhannong Agro Weekly", font=title_font, fill="#006600")
    draw.text((margin, 96), latest, font=subtitle_font, fill="#2d3748")
    draw.text((margin, 136), image_greeting(latest), font=subtitle_font, fill="#4a5568")

    current_y = header_h
    for row_index, pair in enumerate(row_cards):
        row_h = row_heights[row_index]
        current_y += gap
        for col, card in enumerate(pair):
            index = row_index * 2 + col + 1
            x = margin + col * (card_w + gap)
            y = current_y
            tag_color = card_tag_color(card.get("tag"))
            draw.rounded_rectangle((x, y, x + card_w, y + row_h), radius=12, fill="#ffffff", outline="#d8e1ec", width=2)
            draw.rounded_rectangle((x + 18, y + 16, x + 82, y + 44), radius=6, fill=tag_color)
            draw.text((x + 30, y + 19), card_tag_label(card.get("tag")), font=meta_font, fill="#ffffff")

            meta_text = f"{strip_markup(card.get('country', ''))} / {strip_markup(card.get('company', ''))}"
            meta_lines = wrap_text(draw, meta_text, meta_font, card_w - 132)
            meta_y = y + 20
            for line in meta_lines[:2]:
                draw.text((x + 96, meta_y), line, font=meta_font, fill="#718096")
                meta_y += 18

            title_y = draw_wrapped(
                draw,
                f"{index}. {card_title(card)}",
                x + 18,
                y + 58,
                card_title_font,
                "#1a202c",
                card_w - 36,
                30,
            )
            body_y = max(title_y + 10, y + 122)
            link_text = strip_markup(card.get("link", ""))
            body_end_y = draw_wrapped(
                draw,
                strip_markup(card.get("body", "")),
                x + 18,
                body_y,
                body_font,
                "#2d3748",
                card_w - 36,
                line_gap,
            )
            if link_text:
                draw_wrapped(
                    draw,
                    f"출처 링크: {link_text}",
                    x + 18,
                    body_end_y + 10,
                    link_font,
                    "#006600",
                    card_w - 36,
                    20,
                )
        current_y += row_h

    image.save(jpg_path, "JPEG", quality=90, optimize=True)
    return jpg_path


def generate_weekly_assets(latest, cards):
    return generate_weekly_pdf(latest, cards), generate_weekly_jpg(latest, cards)


def build_messages(latest, cards, image_src):
    plain_lines = [
        f"Farmhannong Agro Weekly - {latest}",
        f"사이트: {SITE_URL}",
        "카드뉴스 요약 이미지는 HTML 메일 본문에서 확인하실 수 있으며, 전체 PDF는 첨부파일로 포함되어 있습니다.",
        "",
    ]
    html_lines = [
        f'<p><img src="{escape(image_src, quote=True)}" alt="Farmhannong Agro Weekly {escape(latest)} 요약 모음" style="width:100%;max-width:920px;border:1px solid #d8e1ec;border-radius:10px;"></p>',
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


def write_email_preview(latest, cards, jpg_path):
    # Later this preview writer can be replaced by a server-side approval UI.
    plain_body, html_body = build_messages(latest, cards, jpg_path.name)
    html_path = OUTPUT_DIR / f"Farmhannong_Agro_Weekly_{latest}_email_preview.html"
    txt_path = OUTPUT_DIR / f"Farmhannong_Agro_Weekly_{latest}_email_preview.txt"
    html_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="ko">',
                "<head>",
                '<meta charset="utf-8">',
                f"<title>Farmhannong Agro Weekly {escape(latest)} Email Preview</title>",
                "</head>",
                '<body style="font-family: Arial, sans-serif; max-width: 980px; margin: 24px auto; line-height: 1.55;">',
                html_body,
                "</body>",
                "</html>",
            ]
        ),
        encoding="utf-8",
    )
    txt_path.write_text(plain_body, encoding="utf-8")
    return html_path, txt_path


def configured_smtp():
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT") or "587")
    smtp_user = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user
    return smtp_host, smtp_port, smtp_user, smtp_password, smtp_from


def parse_bool(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def main():
    parser = argparse.ArgumentParser(description="Send the latest Farmhannong Agro Weekly email summary.")
    parser.add_argument("--preview-only", action="store_true", help="Generate the weekly PDF/JPG/HTML/TXT previews without sending email.")
    parser.add_argument("--recipients", help="Optional comma-separated override recipients for a manual test send.")
    parser.add_argument(
        "--require-recipients",
        action="store_true",
        help="Fail instead of skipping when SUMMARY_EMAIL_RECIPIENTS is empty.",
    )
    args = parser.parse_args()

    latest, cards = latest_cards()
    if args.preview_only:
        pdf_path, jpg_path = generate_weekly_assets(latest, cards)
        html_path, txt_path = write_email_preview(latest, cards, jpg_path)
        print(
            json.dumps(
                {
                    "ok": True,
                    "latest": latest,
                    "pdf": str(pdf_path),
                    "jpg": str(jpg_path),
                    "html_preview": str(html_path),
                    "text_preview": str(txt_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    recipients = split_recipients(args.recipients or os.getenv("SUMMARY_EMAIL_RECIPIENTS", ""))
    if not recipients:
        if args.require_recipients or parse_bool(os.getenv("REQUIRE_WEEKLY_EMAIL_RECIPIENTS")) or IS_GITHUB_ACTIONS:
            raise SystemExit("SUMMARY_EMAIL_RECIPIENTS is empty; refusing to silently skip email in GitHub Actions.")
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
        raise SystemExit(f"SMTP is not fully configured; cannot send weekly summary email. Missing: {', '.join(missing)}")

    pdf_path, jpg_path = generate_weekly_assets(latest, cards)
    image_cid = make_msgid(domain="farmhannong-agro-weekly")
    plain_body, html_body = build_messages(latest, cards, f"cid:{image_cid[1:-1]}")

    message = EmailMessage()
    message["Subject"] = f"Ageo weekly 공유 ('{latest}')"
    message["From"] = smtp_from
    message["To"] = ", ".join(recipients)
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")

    html_part = message.get_payload()[-1]
    html_part.add_related(jpg_path.read_bytes(), maintype="image", subtype="jpeg", cid=image_cid)
    message.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=pdf_path.name)

    # 해당 주차의 업로드 원본 리포트 PDF가 있으면 함께 첨부(메일 발송 시에만 — 사이트엔 비제공)
    source_pdfs = source_report_pdfs(latest)
    for src in source_pdfs:
        message.add_attachment(src.read_bytes(), maintype="application", subtype="pdf", filename=src.name)

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

    extra = f" + 원본 리포트 PDF {len(source_pdfs)}건" if source_pdfs else ""
    print(f"Sent weekly summary email to {len(recipients)} recipient(s) with PDF and JPG summary{extra}.")


if __name__ == "__main__":
    main()
