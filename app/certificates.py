from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas


def generate_certificate(name: str, event_name: str, issuer: str) -> bytes:
    output = BytesIO()
    page = landscape(letter)
    pdf = canvas.Canvas(output, pagesize=page)
    width, height = page

    pdf.setFillColor(colors.HexColor("#f8f6ef"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#214e46"))
    pdf.setLineWidth(3)
    pdf.rect(28, 28, width - 56, height - 56, fill=0, stroke=1)
    pdf.setLineWidth(1)
    pdf.rect(36, 36, width - 72, height - 72, fill=0, stroke=1)

    pdf.setFillColor(colors.HexColor("#214e46"))
    pdf.setFont("Times-Bold", 30)
    pdf.drawCentredString(width / 2, height - 150, "CERTIFICATE OF ACHIEVEMENT")
    pdf.setFillColor(colors.HexColor("#343a35"))
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(width / 2, height - 205, "This certificate is proudly presented to")
    pdf.setFillColor(colors.HexColor("#214e46"))
    pdf.setFont("Times-Bold", 34)
    pdf.drawCentredString(width / 2, height - 270, name)
    pdf.setFillColor(colors.HexColor("#343a35"))
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(width / 2, height - 320, f"for completing {event_name}")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawCentredString(width / 2, 105, issuer)
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(width / 2, 86, "AUTHORIZED ISSUER")

    pdf.showPage()
    pdf.save()
    return output.getvalue()