"""
Audit Report PDF Generator
Converts a session audit-report dict (produced by M10) into a
professionally formatted PDF using reportlab.

Usage:
    from utils.report_pdf import build_pdf
    pdf_bytes = build_pdf(report_dict)
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        HRFlowable,
    )
    _REPORTLAB_OK = True
except ImportError:
    _REPORTLAB_OK = False


# ─── colour palette (only initialised when reportlab is available) ─
if _REPORTLAB_OK:
    _BLUE   = colors.HexColor("#1E3A5F")
    _TEAL   = colors.HexColor("#0D9488")
    _LIGHT  = colors.HexColor("#F0F4F8")
    _BORDER = colors.HexColor("#CBD5E1")
    _RED    = colors.HexColor("#DC2626")
    _GREEN  = colors.HexColor("#16A34A")
else:
    _BLUE = _TEAL = _LIGHT = _BORDER = _RED = _GREEN = None  # type: ignore[assignment]


def _fmt(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _money(value: Any, fallback: str = "—") -> str:
    try:
        return f"₹{float(value):,.0f}"
    except (TypeError, ValueError):
        return fallback


def _pct(value: Any, fallback: str = "—") -> str:
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return fallback


def build_pdf(report: dict) -> bytes:
    """
    Build and return PDF bytes for the given audit report dict.
    Raises ImportError if reportlab is not installed.
    Raises RuntimeError on any generation failure.
    """
    if not _REPORTLAB_OK:
        raise ImportError(
            "reportlab is required for PDF export. "
            "Install it with: pip install reportlab>=4.0.0"
        )

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=22 * mm,
        bottomMargin=18 * mm,
    )

    W = A4[0] - 36 * mm  # usable width

    frame = Frame(doc.leftMargin, doc.bottomMargin, W, A4[1] - 40 * mm, id="main")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame)])

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=16, textColor=_BLUE,
                        spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, textColor=_BLUE,
                        spaceBefore=10, spaceAfter=3)
    normal = ParagraphStyle("n", parent=styles["Normal"], fontSize=9, leading=13)
    small  = ParagraphStyle("s", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    code_s = ParagraphStyle("c", parent=styles["Normal"], fontSize=7, fontName="Courier",
                             textColor=colors.HexColor("#374151"), leading=11)

    story = []

    # ── Cover / Header ────────────────────────────────────────────
    story.append(Paragraph("AgentFinance AI — Regulatory Audit Report", h1))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_TEAL, spaceAfter=6))

    meta_rows = [
        ["Report Type", _fmt(report.get("report_type", "regulatory_audit")).replace("_", " ").title()],
        ["Generated At", _fmt(report.get("generated_at"))],
        ["Report Version", _fmt(report.get("version", "1.0"))],
        ["Report Hash (SHA-256)", _fmt(report.get("report_hash", "—"))[:48] + "…"],
    ]
    story.append(_kv_table(meta_rows, W, styles))
    story.append(Spacer(1, 8))

    # ── Session Reference ─────────────────────────────────────────
    sr = report.get("session_reference", {})
    story.append(Paragraph("1. Session Reference", h2))
    rows = [
        ["Session ID",    _fmt(sr.get("session_id"))],
        ["Status",        _fmt(sr.get("status")).upper()],
        ["Created At",    _fmt(sr.get("created_at"))],
        ["IP Address",    _fmt(sr.get("ip_address"))],
        ["Device FP",     (_fmt(sr.get("device_fingerprint")) or "—")[:40]],
    ]
    story.append(_kv_table(rows, W, styles))

    # ── Transcript ────────────────────────────────────────────────
    tr = report.get("transcript", {})
    story.append(Paragraph("2. Transcript Integrity", h2))
    rows = [
        ["SHA-256 Hash",    _fmt(tr.get("transcript_hash"))],
        ["Algorithm",       _fmt(tr.get("hash_algorithm", "SHA-256"))],
        ["Segment Count",   _fmt(tr.get("segment_count", 0))],
    ]
    story.append(_kv_table(rows, W, styles))

    # ── Consent Trail ─────────────────────────────────────────────
    ct = report.get("consent_trail", {})
    story.append(Paragraph("3. Consent Trail", h2))
    obtained = ct.get("consent_obtained", False)
    consent_color = _GREEN if obtained else _RED
    rows = [
        ["Consent Obtained", ("YES" if obtained else "NO")],
    ]
    story.append(_kv_table(rows, W, styles, highlight_last_val=consent_color))
    for rec in (ct.get("records") or []):
        rows2 = [
            ["Type",    _fmt(rec.get("consent_type"))],
            ["Phrase",  _fmt(rec.get("phrase_detected"))],
            ["Hash",    _fmt(rec.get("segment_hash", ""))[:32] + "…"],
            ["Timestamp", _fmt(rec.get("timestamp"))],
        ]
        story.append(_kv_table(rows2, W, styles, indent=True))

    # ── Identity Verification ─────────────────────────────────────
    iv = report.get("identity_verification", {})
    story.append(Paragraph("4. Identity Verification (Liveness)", h2))
    ages = iv.get("age_estimates") or []
    avg_age = (round(sum(ages) / len(ages), 1) if ages else "—")
    rows = [
        ["Frames Analyzed",   _fmt(iv.get("liveness_frames_analyzed", 0))],
        ["Liveness Confirmed", ("YES" if iv.get("liveness_confirmed") else "NO")],
        ["Avg Estimated Age", _fmt(avg_age)],
    ]
    story.append(_kv_table(rows, W, styles))

    # ── Risk Assessment ───────────────────────────────────────────
    ra = report.get("risk_assessment", {})
    llm = ra.get("llm_assessment") or {}
    fraud = ra.get("fraud_scoring") or {}
    story.append(Paragraph("5. Risk Assessment", h2))
    rows = [
        ["Intent Category",    _fmt(llm.get("intent_category", llm.get("intent")))],
        ["Intent Confidence",  _pct((llm.get("intent_confidence") or 0) * 100)],
        ["Risk Persona",       _fmt(llm.get("risk_persona"))],
        ["Risk Confidence",    _pct((llm.get("risk_confidence") or 0) * 100)],
        ["Fraud Score",        _fmt(fraud.get("composite_score"))],
        ["Fraud Risk Level",   _fmt(fraud.get("risk_level", "")).upper()],
        ["Distress Signals",   ("YES" if llm.get("distress_signals") else "NO")],
    ]
    story.append(_kv_table(rows, W, styles))

    if llm.get("reasoning_trace"):
        story.append(Paragraph("LLM Reasoning Trace:", small))
        for line in (llm["reasoning_trace"] or [])[:6]:
            story.append(Paragraph(f"• {_fmt(line)}", code_s))

    # ── Bureau Decision ───────────────────────────────────────────
    bd = report.get("bureau_decision", {})
    story.append(Paragraph("6. Bureau Decision", h2))
    rows = [
        ["Credit Score",        _fmt(bd.get("credit_score"))],
        ["Policy Decision",     _fmt(bd.get("policy_decision", "")).upper()],
        ["Policy Explanation",  _fmt(bd.get("policy_explanation"))],
        ["Fraud Score (used)",  _fmt(bd.get("fraud_score_used_in_bureau"))],
        ["Liveness Avg (used)", _fmt(bd.get("liveness_avg_used_in_bureau"))],
        ["Consent (used)",      ("YES" if bd.get("consent_used_in_bureau") else "NO")],
    ]
    story.append(_kv_table(rows, W, styles))

    # ── Offer Terms ───────────────────────────────────────────────
    ot = report.get("offer_terms", {})
    story.append(Paragraph("7. Loan Offer Terms", h2))
    rows = [
        ["Eligible Amount",    _money(ot.get("eligible_amount"))],
        ["Interest Rate",      _pct(ot.get("interest_rate"))],
        ["Tenure (months)",    _fmt(ot.get("tenure_months"))],
        ["EMI",                _money(ot.get("emi"))],
        ["Offer Status",       _fmt(ot.get("status", "")).upper()],
        ["Accepted At",        _fmt(ot.get("accepted_at"))],
        ["Negotiation Rounds", _fmt(ot.get("negotiation_rounds", 0))],
    ]
    story.append(_kv_table(rows, W, styles))

    # ── Pipeline Trace ────────────────────────────────────────────
    pt = report.get("pipeline_trace", {})
    story.append(Paragraph("8. Pipeline Trace", h2))
    rows = [
        ["Final Stage",        _fmt(pt.get("final_stage"))],
        ["Stages Completed",   ", ".join(pt.get("stages_completed") or []) or "—"],
        ["Stages Failed",      ", ".join(pt.get("stages_failed") or []) or "None"],
    ]
    story.append(_kv_table(rows, W, styles))

    # ── Audit Events Summary ──────────────────────────────────────
    events = report.get("audit_events", [])
    story.append(Paragraph(f"9. Audit Event Log  ({len(events)} events)", h2))
    if events:
        tdata = [["#", "Timestamp", "Module", "Event Type"]]
        for i, evt in enumerate(events[:50], 1):   # cap at 50 rows in PDF
            tdata.append([
                str(i),
                _fmt(evt.get("timestamp", ""))[:19],
                _fmt(evt.get("module")),
                _fmt(evt.get("event_type")),
            ])
        if len(events) > 50:
            tdata.append(["…", f"({len(events) - 50} more events)", "", ""])
        t = Table(tdata, colWidths=[12 * mm, 48 * mm, 28 * mm, W - 88 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTSIZE",   (0, 0), (-1, -1), 7),
            ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.3, _BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No audit events recorded.", normal))

    # ── Footer note ───────────────────────────────────────────────
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_BORDER))
    story.append(Paragraph(
        f"Generated by AgentFinance AI Compliance Engine · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}  "
        "· This document is auto-generated and cryptographically signed.",
        small,
    ))

    doc.build(story)
    return buf.getvalue()


# ─── Internal table builder ───────────────────────────────────────

def _kv_table(
    rows: list[list[str]],
    width: float,
    styles: Any,
    indent: bool = False,
    highlight_last_val: Any = None,
) -> Table:
    col_w = [52 * mm, width - 52 * mm - (8 * mm if indent else 0)]
    if indent:
        col_w = [8 * mm] + col_w
        rows = [["", r[0], r[1]] for r in rows]

    t = Table(rows, colWidths=col_w)
    ts = [
        ("FONTSIZE",  (0, 0), (-1, -1), 8),
        ("FONTNAME",  (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), _BLUE),
        ("VALIGN",    (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.3, _BORDER),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]
    if highlight_last_val is not None:
        last_col = -1
        last_row = len(rows) - 1
        ts.append(("TEXTCOLOR", (last_col, last_row), (last_col, last_row), highlight_last_val))
        ts.append(("FONTNAME",  (last_col, last_row), (last_col, last_row), "Helvetica-Bold"))
    t.setStyle(TableStyle(ts))
    return t
