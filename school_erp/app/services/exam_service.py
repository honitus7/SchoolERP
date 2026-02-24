from __future__ import annotations

from app.extensions import db
from app.models.exams import Exam, ExamSubject, Mark, ReportCard, ReportCardItem


def create_exam(tenant_id: int, name: str, class_id: int):
    exam = Exam(tenant_id=tenant_id, name=name, class_id=class_id, status="draft")
    db.session.add(exam)
    db.session.commit()
    return exam


def schedule_exam(exam: Exam, start_date, end_date):
    exam.scheduled_from = start_date
    exam.scheduled_to = end_date
    exam.status = "scheduled"
    db.session.commit()
    return exam


def add_marks(tenant_id: int, exam_id: int, subject_id: int, entries: list[dict]):
    exam_subject = ExamSubject.query.filter_by(exam_id=exam_id, subject_id=subject_id).first()
    if not exam_subject:
        exam_subject = ExamSubject(tenant_id=tenant_id, exam_id=exam_id, subject_id=subject_id, max_marks=100)
        db.session.add(exam_subject)
        db.session.flush()

    for entry in entries:
        mark = Mark.query.filter_by(exam_subject_id=exam_subject.id, student_id=entry["student_id"]).first()
        if not mark:
            mark = Mark(
                tenant_id=tenant_id,
                exam_subject_id=exam_subject.id,
                student_id=entry["student_id"],
                marks_obtained=entry["marks_obtained"],
                grade=entry.get("grade"),
            )
            db.session.add(mark)
        else:
            mark.marks_obtained = entry["marks_obtained"]
            mark.grade = entry.get("grade", mark.grade)
    db.session.commit()
    return exam_subject


def publish_report_cards(tenant_id: int, exam_id: int):
    marks = (
        db.session.query(Mark)
        .join(ExamSubject, Mark.exam_subject_id == ExamSubject.id)
        .filter(ExamSubject.exam_id == exam_id, Mark.tenant_id == tenant_id)
        .all()
    )

    grouped = {}
    for mark in marks:
        grouped.setdefault(mark.student_id, []).append(mark)

    published = []
    for student_id, student_marks in grouped.items():
        total = sum(m.marks_obtained for m in student_marks)
        max_marks = sum(m.exam_subject.max_marks for m in student_marks)
        percentage = (total / max_marks * 100) if max_marks else 0

        card = ReportCard.query.filter_by(tenant_id=tenant_id, student_id=student_id, exam_id=exam_id).first()
        if not card:
            card = ReportCard(
                tenant_id=tenant_id,
                student_id=student_id,
                exam_id=exam_id,
                total_marks=total,
                percentage=percentage,
                status="published",
            )
            db.session.add(card)
            db.session.flush()
        else:
            card.total_marks = total
            card.percentage = percentage
            card.status = "published"

        ReportCardItem.query.filter_by(report_card_id=card.id).delete()
        for m in student_marks:
            db.session.add(
                ReportCardItem(
                    tenant_id=tenant_id,
                    report_card_id=card.id,
                    subject_id=m.exam_subject.subject_id,
                    marks_obtained=m.marks_obtained,
                    max_marks=m.exam_subject.max_marks,
                    grade=m.grade,
                )
            )
        published.append(card)

    exam = db.session.get(Exam, exam_id)
    if exam:
        exam.status = "published"

    db.session.commit()
    return published
