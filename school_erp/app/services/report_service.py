from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def render_report_card_pdf(student_name: str, exam_name: str, items: list[dict], total: float, percentage: float) -> bytes:
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    pdf.setTitle(f"Report Card - {student_name}")

    y = 800
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, y, "School ERP Report Card")
    y -= 30
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, y, f"Student: {student_name}")
    y -= 20
    pdf.drawString(50, y, f"Exam: {exam_name}")
    y -= 30

    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Subject")
    pdf.drawString(250, y, "Marks")
    pdf.drawString(350, y, "Max")
    pdf.drawString(450, y, "Grade")
    y -= 20

    pdf.setFont("Helvetica", 11)
    for item in items:
        pdf.drawString(50, y, item["subject"])
        pdf.drawString(250, y, str(item["marks_obtained"]))
        pdf.drawString(350, y, str(item["max_marks"]))
        pdf.drawString(450, y, item.get("grade") or "-")
        y -= 18
        if y < 100:
            pdf.showPage()
            y = 800

    y -= 16
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(50, y, f"Total: {total}")
    y -= 20
    pdf.drawString(50, y, f"Percentage: {percentage:.2f}%")

    pdf.showPage()
    pdf.save()
    stream.seek(0)
    return stream.read()
