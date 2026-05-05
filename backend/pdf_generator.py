from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER


def generate_delivery_slip(order: dict) -> bytes:
    """Generate a printable delivery slip PDF from an extracted order. Returns bytes."""

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=22,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=18,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
        spaceBefore=12,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#64748b"),
    )
    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )

    story = []

    # Header
    story.append(Paragraph("BON DE LIVRAISON", title_style))
    story.append(Paragraph(
        f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))

    # Customer section
    story.append(Paragraph("CLIENT", section_style))
    story.append(_field("Nom", order.get("customer_name"), label_style, value_style))
    story.append(_field("Téléphone", order.get("phone"), label_style, value_style))
    story.append(_field("Gouvernorat", order.get("governorate"), label_style, value_style))
    story.append(_field("Adresse", order.get("address"), label_style, value_style))

    # Items section
    story.append(Paragraph("ARTICLES", section_style))
    items = order.get("items", []) or []
    if items:
        story.append(_items_table(items))
    else:
        story.append(Paragraph("Aucun article", value_style))

    # Total
    if order.get("total_price"):
        story.append(Spacer(1, 0.3 * cm))
        total_para = Paragraph(
            f"<b>Total : {order['total_price']} TND</b>",
            ParagraphStyle("Total", parent=value_style, fontSize=13, alignment=TA_LEFT),
        )
        story.append(total_para)

    # Notes
    if order.get("notes"):
        story.append(Paragraph("NOTES", section_style))
        story.append(Paragraph(order["notes"], value_style))

    # Footer
    story.append(Spacer(1, 1.5 * cm))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e2e8f0")))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Généré avec DM2Order — dm2order.tn",
        ParagraphStyle("Footer", parent=label_style, alignment=TA_CENTER),
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


def _field(label: str, value, label_style, value_style):
    """Render a label-and-value pair as a Paragraph."""
    display = value if value not in (None, "", []) else "—"
    return Paragraph(
        f'<font color="#64748b" size="8">{label.upper()}</font><br/>{display}',
        value_style,
    )


def _items_table(items):
    """Build the items table."""
    data = [["Produit", "Variante", "Qté", "Prix"]]
    for item in items:
        data.append([
            item.get("product") or "—",
            item.get("variant") or "—",
            str(item.get("quantity", 1)),
            f"{item['price']} TND" if item.get("price") else "—",
        ])

    table = Table(data, colWidths=[7 * cm, 4.5 * cm, 1.5 * cm, 3 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#475569")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (2, 0), (3, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#cbd5e1")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    return table