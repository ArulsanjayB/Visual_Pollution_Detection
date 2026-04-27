"""
Report service — business logic for priority scoring, PDF generation, and rewards.
"""
import io
from datetime import datetime
from typing import Optional


# ── Priority scoring ──────────────────────────────────────────────────────────

# Class urgency weights (potholes block traffic, debris is hazardous, vehicles block spaces)
CLASS_URGENCY = {"Potholes": 0.8, "Abandoned_Vehicles": 0.6, "Construction_Debris": 0.7}
REWARD_TOKENS_ON_RESOLVE = 10


def build_priority_score(inference_result: dict) -> float:
    """
    Composite priority score [0–100] for municipal queue ordering.

    Formula:
        P = 40*confidence + 30*severity_weight + 20*class_urgency + 10*count_factor
    """
    conf = inference_result.get("confidence", 0)
    severity_weight = {"LOW": 0.3, "MEDIUM": 0.6, "HIGH": 1.0}.get(
        inference_result.get("severity", "LOW"), 0.3
    )
    cls = inference_result.get("primary_class", "Potholes")
    class_urgency = CLASS_URGENCY.get(cls, 0.5)
    count = min(inference_result.get("num_detections", 1) / 5.0, 1.0)

    score = 40 * conf + 30 * severity_weight + 20 * class_urgency + 10 * count
    return round(score, 2)


# ── Reward system ─────────────────────────────────────────────────────────────

async def issue_reward_if_resolved(citizen_uid: Optional[str], report_id: str, db):
    """Issue reward tokens to citizen when their report is resolved."""
    if not citizen_uid:
        return
    try:
        user_ref = db.collection("users").document(citizen_uid)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return
        user_data = user_doc.to_dict()
        current_tokens = user_data.get("total_tokens", 0)
        resolved_count = user_data.get("resolved_reports", 0)
        user_ref.update({
            "total_tokens": current_tokens + REWARD_TOKENS_ON_RESOLVE,
            "resolved_reports": resolved_count + 1,
        })
        # Mark reward on report
        db.collection("reports").document(report_id).update({
            "reward_issued": True,
            "reward_tokens": REWARD_TOKENS_ON_RESOLVE,
        })
    except Exception as e:
        print(f"Reward issuance failed for {citizen_uid}: {e}")


# ── PDF report generation ─────────────────────────────────────────────────────

async def generate_pdf_report(report_data: dict) -> bytes:
    """
    Generate a professional PDF report for municipal authorities.
    Includes: detection summary, XAI explanation, location, timestamps.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
    from reportlab.lib.units import cm
    import base64, tempfile, os

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                             leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=18,
                                  textColor=colors.HexColor("#1a237e"), spaceAfter=4)
    story.append(Paragraph("Visual Pollution Incident Report", title_style))
    story.append(Paragraph("Municipal Authority — AI-Assisted Detection System", styles["Normal"]))
    story.append(Spacer(1, 0.4*cm))

    # ── Report metadata ───────────────────────────────────────────────────────
    inf = report_data.get("inference") or {}
    loc = report_data.get("location") or {}
    created = report_data.get("created_at", "")
    if hasattr(created, 'isoformat'):
        created = created.isoformat()

    meta_data = [
        ["Report ID",    str(report_data.get("id", ""))[:16]],
        ["Date & Time",  str(created)[:19].replace("T", " ")],
        ["Status",       str(report_data.get("status", "pending")).upper()],
        ["Reported by",  report_data.get("citizen_name", "Citizen")],
        ["Location",     f"Lat: {loc.get('latitude','N/A')}, Lng: {loc.get('longitude','N/A')}"],
        ["Address",      loc.get("address", "Not provided")],
    ]
    meta_table = Table(meta_data, colWidths=[4.5*cm, 12*cm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8eaf6")),
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("PADDING",    (0, 0), (-1, -1), 5),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5*cm))

    # ── AI Detection Results ──────────────────────────────────────────────────
    story.append(Paragraph("AI Detection Results", styles["Heading2"]))
    severity_color = {"HIGH": "#c62828", "MEDIUM": "#f57f17", "LOW": "#2e7d32"}.get(
        inf.get("severity", "LOW"), "#000000"
    )
    sev_style = ParagraphStyle("sev", parent=styles["Normal"],
                                textColor=colors.HexColor(severity_color), fontSize=12)
    story.append(Paragraph(f"<b>Severity: {inf.get('severity','LOW')}</b>", sev_style))

    ai_data = [
        ["Pollution Type",    inf.get("primary_class", "Unknown")],
        ["Confidence Score",  f"{inf.get('confidence', 0)*100:.1f}%"],
        ["Detections Found",  str(inf.get("num_detections", 0))],
        ["Priority Score",    f"{report_data.get('priority_score', 0):.1f} / 100"],
        ["XAI Method",        inf.get("xai", {}).get("method", "gradcam").upper()],
        ["Inference Time",    f"{inf.get('inference_time_ms', 0)} ms"],
    ]
    ai_table = Table(ai_data, colWidths=[5*cm, 11.5*cm])
    ai_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#fce4ec")),
        ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#fff9c4")]),
        ("PADDING",    (0, 0), (-1, -1), 5),
    ]))
    story.append(ai_table)
    story.append(Spacer(1, 0.5*cm))

    # ── Detections detail ─────────────────────────────────────────────────────
    boxes = inf.get("detections", [])
    if boxes:
        story.append(Paragraph("Detection Details", styles["Heading3"]))
        det_rows = [["#", "Class", "Confidence", "BBox (x1,y1,x2,y2)"]]
        for i, b in enumerate(boxes, 1):
            bbox = b.get("bbox", [])
            bbox_str = ",".join(f"{v:.0f}" for v in bbox) if bbox else "N/A"
            det_rows.append([str(i), b.get("class_name","?"), f"{b.get('confidence',0)*100:.1f}%", bbox_str])
        det_table = Table(det_rows, colWidths=[1*cm, 5*cm, 4*cm, 6.5*cm])
        det_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("FONTNAME",   (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("PADDING",    (0, 0), (-1, -1), 4),
        ]))
        story.append(det_table)
        story.append(Spacer(1, 0.4*cm))

    # ── XAI Explanation ───────────────────────────────────────────────────────
    story.append(Paragraph("Explainable AI (XAI) Summary", styles["Heading2"]))
    xai_meta = inf.get("xai", {}).get("metadata", {})
    method = inf.get("xai", {}).get("method", "gradcam")

    xai_text = {
        "gradcam": "Grad-CAM heatmap highlights spatial regions whose activation gradients most strongly influenced the model's prediction. Red/yellow areas indicate high importance.",
        "lime": "LIME superpixel analysis identifies semantic image regions (green) supporting the detection and regions (red) opposing it.",
        "zoolime": "ZooLime fusion combines Grad-CAM spatial precision with LIME semantic interpretability. The fused map shows consensus regions that both methods identify as critical — providing the most reliable explanation.",
        "shap": "SHAP Gradient values show per-pixel contribution to the model output. Brighter regions indicate higher Shapley value (positive impact on confidence).",
    }
    story.append(Paragraph(xai_text.get(method, "AI explanation generated."), styles["Normal"]))

    if method == "zoolime":
        story.append(Spacer(1, 0.2*cm))
        story.append(Paragraph(
            f"<b>Fusion Parameters:</b> α(Grad-CAM weight)={xai_meta.get('alpha',0.6)}, "
            f"β(agreement boost)={xai_meta.get('beta',0.3)}, "
            f"Grad-CAM↔LIME correlation={xai_meta.get('correlation',0):.3f}",
            styles["Normal"]
        ))

    # ── XAI overlay image (if available as URL) ───────────────────────────────
    overlay_url = report_data.get("gradcam_url") or report_data.get("zoolime_url")
    if overlay_url and overlay_url.startswith("/storage"):
        # Local storage: try to embed
        try:
            from app.config import settings
            local_path = str(settings.local_storage_path) + overlay_url.replace("/storage", "")
            if os.path.exists(local_path):
                img = RLImage(local_path, width=10*cm, height=7*cm)
                story.append(Spacer(1, 0.3*cm))
                story.append(Paragraph("<b>XAI Visualization:</b>", styles["Normal"]))
                story.append(img)
        except Exception:
            pass

    story.append(Spacer(1, 0.5*cm))

    # ── Notes ─────────────────────────────────────────────────────────────────
    if report_data.get("municipal_notes"):
        story.append(Paragraph("Municipal Notes", styles["Heading3"]))
        story.append(Paragraph(report_data["municipal_notes"], styles["Normal"]))
        story.append(Spacer(1, 0.3*cm))

    # ── Footer ────────────────────────────────────────────────────────────────
    footer_style = ParagraphStyle("footer", parent=styles["Normal"], fontSize=7,
                                   textColor=colors.grey)
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | "
        "Visual Pollution Detector v1.0 | AI-assisted — human review recommended",
        footer_style
    ))

    doc.build(story)
    return buf.getvalue()
