#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "index.html"
OUTPUT_ROOT = REPO_ROOT / "source-pdfs"


def parse_news_database():
    text = INDEX_PATH.read_text(encoding="utf-8")
    marker = "const newsDatabase = "
    start = text.index(marker) + len(marker)
    end = text.index(";\n        let allDates", start)
    return json.loads(text[start:end])


def strip_markup(value):
    text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def source_pdf_path(date_key, index):
    return OUTPUT_ROOT / date_key / f"{index + 1:02d}.pdf"


def build_search_url(item):
    title = item.get("raw_title") or re.sub(r"^\d+\.\s*", "", item.get("title", ""))
    source = item.get("source") or ""
    return "https://www.google.com/search?q=" + quote_plus(f'"{title}" {source}'.strip())


def paragraph(text, style):
    safe = html.escape(strip_markup(text)).replace("\n", "<br/>")
    return Paragraph(safe or "-", style)


def generate_pdf(date_key, index, item, generated_at):
    target = source_pdf_path(date_key, index)
    target.parent.mkdir(parents=True, exist_ok=True)

    pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "KoreanTitle",
        parent=styles["Title"],
        fontName="HYGothic-Medium",
        fontSize=17,
        leading=22,
        textColor=colors.HexColor("#006600"),
        alignment=TA_LEFT,
        spaceAfter=10,
        wordWrap="CJK",
    )
    label_style = ParagraphStyle(
        "KoreanLabel",
        parent=styles["Normal"],
        fontName="HYGothic-Medium",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#2D3748"),
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "KoreanBody",
        parent=styles["BodyText"],
        fontName="HYSMyeongJo-Medium",
        fontSize=9,
        leading=14,
        textColor=colors.HexColor("#2D3748"),
        wordWrap="CJK",
    )
    note_style = ParagraphStyle(
        "KoreanNote",
        parent=styles["BodyText"],
        fontName="HYGothic-Medium",
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#718096"),
        wordWrap="CJK",
    )

    original_url = item.get("link") or ""
    search_url = build_search_url(item)
    title = item.get("raw_title") or re.sub(r"^\d+\.\s*", "", item.get("title", ""))
    summary = item.get("raw_body") or item.get("body") or ""

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Source Evidence {date_key} #{index + 1:02d}",
        author="Farmhannong Agro Weekly",
    )

    story = [
        Paragraph("Farmhannong Agro Weekly - 출처 확인용 PDF", title_style),
        Paragraph(
            "이 파일은 원문 기사 전체를 복제한 보관본이 아니라, 링크 차단/삭제 시에도 출처 확인을 돕기 위한 색인 PDF입니다.",
            note_style,
        ),
        Spacer(1, 8),
    ]

    rows = [
        ["카드 발행일", date_key],
        ["카드 번호", str(index + 1)],
        ["출처", item.get("source") or ""],
        ["원문 제목", title],
        ["원 URL", original_url],
        ["제목 검색 URL", search_url],
        ["검색 키워드", item.get("search_keywords") or ""],
        ["PDF 생성일", generated_at],
    ]
    table_data = [[Paragraph(html.escape(k), label_style), paragraph(v, body_style)] for k, v in rows]
    table = Table(table_data, colWidths=[32 * mm, 130 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E6F2E6")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#006600")),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E2E8F0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Paragraph("카드 요약 / 당시 확인 내용", label_style))
    story.append(Spacer(1, 4))
    story.append(paragraph(summary, body_style))

    doc.build(story)
    return target


def main():
    db = parse_news_database()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    created = []
    for date_key, items in db.items():
        for index, item in enumerate(items):
            if item.get("raw_title") or item.get("raw_body") or item.get("search_keywords"):
                created.append(generate_pdf(date_key, index, item, generated_at))

    print(json.dumps({"created": len(created), "root": str(OUTPUT_ROOT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
