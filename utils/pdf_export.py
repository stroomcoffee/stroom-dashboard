"""
Generate PDF ringkasan dashboard menggunakan ReportLab.
"""
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                 TableStyle, HRFlowable)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# Dark-ish palette (PDF pakai warna gelap di teks, background putih)
C_ACCENT  = colors.HexColor("#00C896")
C_ACCENT2 = colors.HexColor("#3D8EF0")
C_DARK    = colors.HexColor("#0F1117")
C_MUTED   = colors.HexColor("#5A5F7A")
C_BORDER  = colors.HexColor("#E2E4EE")
C_WARN    = colors.HexColor("#F5A623")
C_DANGER  = colors.HexColor("#F04D4D")
C_BG_ROW  = colors.HexColor("#F7F8FC")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold",
                                fontSize=22, textColor=C_DARK, spaceAfter=4),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica",
                                   fontSize=9, textColor=C_MUTED, spaceAfter=14),
        "section": ParagraphStyle("section", fontName="Helvetica-Bold",
                                  fontSize=11, textColor=C_DARK, spaceBefore=14, spaceAfter=6),
        "label": ParagraphStyle("label", fontName="Helvetica",
                                fontSize=8, textColor=C_MUTED),
        "value": ParagraphStyle("value", fontName="Helvetica-Bold",
                                fontSize=16, textColor=C_DARK),
        "body": ParagraphStyle("body", fontName="Helvetica",
                               fontSize=9, textColor=C_DARK),
        "caption": ParagraphStyle("caption", fontName="Helvetica",
                                  fontSize=7.5, textColor=C_MUTED),
    }


def _kpi_table(kpis, styles):
    """kpis: list of (label, value, sub) tuples, max 4 per row"""
    cell_data = []
    labels_row = []
    values_row = []
    for label, value, sub in kpis:
        labels_row.append(Paragraph(label, styles["label"]))
        v_para = Paragraph(value, styles["value"])
        s_para = Paragraph(sub, styles["caption"]) if sub else Paragraph("", styles["caption"])
        values_row.append([v_para, s_para])

    # Build as nested table per cell
    cells = []
    for label, value, sub in kpis:
        inner = Table(
            [[Paragraph(label, styles["label"])],
             [Paragraph(value, styles["value"])],
             [Paragraph(sub or "", styles["caption"])]],
            colWidths=["100%"]
        )
        inner.setStyle(TableStyle([
            ("LEFTPADDING", (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
            ("TOPPADDING", (0,0), (-1,-1), 1),
            ("BOTTOMPADDING", (0,0), (-1,-1), 1),
        ]))
        cells.append(inner)

    col_w = (A4[0] - 30*mm) / len(cells)
    t = Table([cells], colWidths=[col_w]*len(cells))
    t.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.5, C_BORDER),
        ("INNERGRID", (0,0), (-1,-1), 0.5, C_BORDER),
        ("BACKGROUND", (0,0), (-1,-1), colors.white),
        ("TOPPADDING", (0,0), (-1,-1), 10),
        ("BOTTOMPADDING", (0,0), (-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 12),
        ("RIGHTPADDING", (0,0), (-1,-1), 12),
        ("ROUNDEDCORNERS", [6]),
    ]))
    return t


def _data_table(headers, rows, styles, col_widths=None):
    data = [[Paragraph(h, ParagraphStyle("th", fontName="Helvetica-Bold",
                                          fontSize=8, textColor=C_MUTED)) for h in headers]]
    for i, row in enumerate(rows):
        data.append([Paragraph(str(c), ParagraphStyle("td", fontName="Helvetica",
                                                       fontSize=8.5, textColor=C_DARK)) for c in row])
    w = A4[0] - 30*mm
    if col_widths is None:
        col_widths = [w / len(headers)] * len(headers)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0,0), (-1,0), C_BG_ROW),
        ("LINEBELOW", (0,0), (-1,0), 0.5, C_BORDER),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, C_BG_ROW]),
        ("LINEBELOW", (0,1), (-1,-1), 0.3, C_BORDER),
    ])
    t.setStyle(style)
    return t


def generate_dashboard_pdf(data: dict) -> bytes:
    """
    data keys:
      date_range, net_sales, gross_sales, total_disc, total_tx,
      total_qty, avg_tx, total_bahan, stok_negatif,
      top_menu (df), sales_by_cat (df), po_summary (df), stock_alerts (df)
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm,
                            topMargin=15*mm, bottomMargin=15*mm)
    styles = _styles()
    story = []

    # ── Header ─────────────────────────────────────────────────────
    story.append(Paragraph("Stroom Inventory", styles["title"]))
    d = data.get("date_range", "")
    story.append(Paragraph(f"Laporan Dashboard · {d} · Dicetak {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                           styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceAfter=10))

    # ── KPI Row 1 ───────────────────────────────────────────────────
    story.append(Paragraph("Ringkasan Penjualan", styles["section"]))
    story.append(_kpi_table([
        ("Net Sales",       data["net_sales"],    ""),
        ("Gross Sales",     data["gross_sales"],  ""),
        ("Total Diskon",    data["total_disc"],   ""),
        ("Total Transaksi", data["total_tx"],     ""),
    ], styles))
    story.append(Spacer(1, 6))
    story.append(_kpi_table([
        ("Item Terjual",    data["total_qty"],    ""),
        ("Avg/Transaksi",   data["avg_tx"],       ""),
        ("Jenis Bahan",     data["total_bahan"],  ""),
        ("Stok Negatif",    data["stok_negatif"], ""),
    ], styles))

    # ── Top Menu ───────────────────────────────────────────────────
    df_top = data.get("top_menu")
    if df_top is not None and not df_top.empty:
        story.append(Paragraph("Top 15 Menu Terlaris", styles["section"]))
        rows = [(r["item_name"], f"{int(r['qty']):,}", r["sales"])
                for _, r in df_top.head(15).iterrows()]
        w = A4[0] - 30*mm
        story.append(_data_table(
            ["Menu", "Qty Terjual", "Net Sales"], rows, styles,
            col_widths=[w*0.55, w*0.2, w*0.25]
        ))

    # ── Sales by Category ──────────────────────────────────────────
    df_cat = data.get("sales_by_cat")
    if df_cat is not None and not df_cat.empty:
        story.append(Paragraph("Penjualan per Kategori", styles["section"]))
        rows = [(r["category"], r["total"]) for _, r in df_cat.iterrows()]
        w = A4[0] - 30*mm
        story.append(_data_table(
            ["Kategori", "Net Sales"], rows, styles,
            col_widths=[w*0.5, w*0.5]
        ))

    # ── PO Summary ────────────────────────────────────────────────
    df_po = data.get("po_summary")
    if df_po is not None and not df_po.empty:
        story.append(Paragraph("Ringkasan Purchase Order", styles["section"]))
        rows = [(r["status"], f"{int(r['jml_po']):,}", r["nilai"]) for _, r in df_po.iterrows()]
        w = A4[0] - 30*mm
        story.append(_data_table(
            ["Status", "Jumlah PO", "Total Nilai"], rows, styles,
            col_widths=[w*0.4, w*0.2, w*0.4]
        ))

    # ── Stock Alerts ──────────────────────────────────────────────
    df_alert = data.get("stock_alerts")
    if df_alert is not None and not df_alert.empty:
        story.append(Paragraph("Alert Stok Bahan (< 1000)", styles["section"]))
        rows = []
        for _, r in df_alert.iterrows():
            v = r["stok_final"]
            status = "🔴 Negatif" if v < 0 else ("🟡 Rendah" if v < 300 else "🟢 Menengah")
            src = "Adjustment" if r["stok_source"] == "adjusted" else "PO"
            rows.append((r["ingredient_name"], f"{v:,.1f}", r["unit"], status, src))
        w = A4[0] - 30*mm
        story.append(_data_table(
            ["Bahan", "Stok", "Satuan", "Status", "Sumber"], rows, styles,
            col_widths=[w*0.35, w*0.15, w*0.15, w*0.2, w*0.15]
        ))

    # ── Footer ────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Stroom Coffee · Jakarta Gambir · Generated by Stroom Inventory System",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=7.5, textColor=C_MUTED, alignment=TA_CENTER)
    ))

    doc.build(story)
    return buf.getvalue()
