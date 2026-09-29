"""Season summary PDF generation for RowSeer (reportlab)."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from metrics import best_pace, pace_per_500m

TYPE_LABELS = {"water": "Water", "erg": "Erg", "race": "Race"}
RECENT_LIMIT = 20


def _type_label(value: object) -> str:
    key = str(value or "").lower().strip()
    return TYPE_LABELS.get(key, str(value).title() if value else "")


def build_season_pdf(email: str, frame: pd.DataFrame) -> bytes:
    """Build a simple season summary PDF; returns PDF bytes."""
    if frame is None or not hasattr(frame, "columns") or frame.empty:
        work = pd.DataFrame(
            columns=["date", "type", "distance_m", "time_sec", "notes"]
        )
    else:
        work = frame.copy()

    total_meters = int(pd.to_numeric(work["distance_m"], errors="coerce").fillna(0).sum()) if not work.empty else 0
    practice_count = len(work)
    pace_1k = best_pace(work, 1000) if not work.empty else None
    pace_2k = best_pace(work, 2000) if not work.empty else None

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="RowSeer Season Summary",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SeasonTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "SeasonSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        spaceAfter=16,
    )
    body = ParagraphStyle(
        "SeasonBody",
        parent=styles["Normal"],
        fontSize=11,
        leading=16,
        spaceAfter=4,
    )
    section = ParagraphStyle(
        "SeasonSection",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=14,
        spaceAfter=8,
    )

    story: list = [
        Paragraph("RowSeer — Season Summary", title_style),
        Paragraph(f"Generated {date.today().isoformat()}", subtitle_style),
        Paragraph(f"<b>Athlete:</b> {email or '—'}", body),
        Paragraph(f"<b>Total meters:</b> {total_meters:,}", body),
        Paragraph(f"<b>Practices:</b> {practice_count}", body),
        Paragraph(f"<b>Best /500m (≥1,000m):</b> {pace_1k or '—'}", body),
        Paragraph(f"<b>Best /500m (≥2,000m):</b> {pace_2k or '—'}", body),
        Paragraph("Recent practices", section),
    ]

    if work.empty:
        story.append(Paragraph("No practices logged yet.", body))
    else:
        recent = work.copy()
        recent["date"] = pd.to_datetime(recent["date"], errors="coerce")
        recent = recent.sort_values("date", ascending=False, na_position="last").head(RECENT_LIMIT)
        table_data = [["Date", "Type", "Distance (m)", "Time (s)", "Pace /500m", "Notes"]]
        for _, row in recent.iterrows():
            dt = row.get("date")
            date_str = pd.Timestamp(dt).strftime("%Y-%m-%d") if pd.notna(dt) else ""
            dist = int(pd.to_numeric(row.get("distance_m"), errors="coerce") or 0)
            tsec = int(pd.to_numeric(row.get("time_sec"), errors="coerce") or 0)
            pace = pace_per_500m(dist, tsec) or "—"
            notes = str(row.get("notes") or "")
            if len(notes) > 40:
                notes = notes[:37] + "..."
            table_data.append(
                [
                    date_str,
                    _type_label(row.get("type")),
                    f"{dist:,}",
                    str(tsec),
                    pace,
                    notes,
                ]
            )
        table = Table(
            table_data,
            colWidths=[0.9 * inch, 0.7 * inch, 1.0 * inch, 0.75 * inch, 0.9 * inch, 2.3 * inch],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (2, 1), (4, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8fb")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)
        if practice_count > RECENT_LIMIT:
            story.append(Spacer(1, 8))
            story.append(
                Paragraph(
                    f"Showing {RECENT_LIMIT} most recent of {practice_count} practices.",
                    subtitle_style,
                )
            )

    doc.build(story)
    return buffer.getvalue()
