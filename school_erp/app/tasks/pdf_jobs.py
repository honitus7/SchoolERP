from __future__ import annotations

from app.services.report_service import render_report_card_pdf


def create_report_pdf(student_name: str, exam_name: str, items: list[dict], total: float, percentage: float) -> bytes:
    return render_report_card_pdf(student_name, exam_name, items, total, percentage)
