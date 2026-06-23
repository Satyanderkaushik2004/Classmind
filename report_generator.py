import io
import time
import zipfile
import csv
import openpyxl
from datetime import datetime
from typing import List

# ReportLab imports
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def get_pdf_styles():
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1e293b'),
        alignment=0, # Left-aligned
        spaceAfter=6
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=15
    )
    
    section_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=12,
        spaceAfter=8
    )

    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#334155')
    )

    cell_style_bold = ParagraphStyle(
        'TableCellBold',
        parent=cell_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a')
    )

    header_style = ParagraphStyle(
        'TableHeaderCell',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.white
    )

    stat_label_style = ParagraphStyle(
        'StatLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#475569')
    )
    
    stat_val_style = ParagraphStyle(
        'StatValue',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#0f172a')
    )

    return {
        "title": title_style,
        "subtitle": subtitle_style,
        "section": section_style,
        "cell": cell_style,
        "cell_bold": cell_style_bold,
        "header": header_style,
        "stat_label": stat_label_style,
        "stat_val": stat_val_style
    }

def generate_gradebook_pdf(session_code: str, session_name: str, teacher_name: str, created_at: float, students_data: List[dict]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = get_pdf_styles()

    # Title & Header
    story.append(Paragraph(f"📊 Student Marks Register", styles["title"]))
    date_str = datetime.fromtimestamp(created_at).strftime('%d %B %Y')
    story.append(Paragraph(f"Session: {session_name} ({session_code})  |  Teacher: {teacher_name}  |  Date: {date_str}", styles["subtitle"]))
    story.append(Spacer(1, 10))

    # Table construction
    headers = [
        Paragraph("Rank", styles["header"]),
        Paragraph("Student Name", styles["header"]),
        Paragraph("Roll No", styles["header"]),
        Paragraph("Class", styles["header"]),
        Paragraph("Task %", styles["header"]),
        Paragraph("Test Score", styles["header"]),
        Paragraph("Coding Score", styles["header"]),
        Paragraph("Overall %", styles["header"])
    ]
    
    table_data = [headers]
    for s in students_data:
        table_data.append([
            Paragraph(str(s.get("rank", "—")), styles["cell_bold"]),
            Paragraph(s.get("name", "Student"), styles["cell_bold"]),
            Paragraph(s.get("roll_no", "—"), styles["cell"]),
            Paragraph(s.get("class_name", "—"), styles["cell"]),
            Paragraph(f"{s.get('task_score', 0)}%", styles["cell"]),
            Paragraph(str(s.get("test_score", "—")), styles["cell"]),
            Paragraph(f"{s.get('coding_score', 0)}%" if s.get("coding_submitted") else "—", styles["cell"]),
            Paragraph(f"{s.get('overall_percentage', 0)}%", styles["cell_bold"])
        ])

    col_widths = [40, 150, 60, 60, 60, 60, 60, 50]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    t_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
    ])
    t.setStyle(t_style)
    story.append(t)

    doc.build(story)
    return buffer.getvalue()

def generate_task_pdf(session_code: str, task_index: int, question: str, topic: str, max_marks: int, students_data: List[dict]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = get_pdf_styles()

    story.append(Paragraph(f"📋 Task Report — Task #{task_index}", styles["title"]))
    story.append(Paragraph(f"Session Code: {session_code}  |  Topic: {topic}  |  Max Marks: {max_marks}", styles["subtitle"]))
    story.append(Paragraph(f"<b>Question:</b> {question}", styles["subtitle"]))
    story.append(Spacer(1, 10))

    headers = [
        Paragraph("Student Name", styles["header"]),
        Paragraph("Marks Obtained", styles["header"]),
        Paragraph("Total Marks", styles["header"]),
        Paragraph("Percentage", styles["header"]),
        Paragraph("Submission Status", styles["header"]),
        Paragraph("Submission Time", styles["header"])
    ]
    
    table_data = [headers]
    for s in students_data:
        pct_str = f"{s.get('percentage', 0)}%" if s.get("status") == "Submitted" else "—"
        table_data.append([
            Paragraph(s.get("name", "Student"), styles["cell_bold"]),
            Paragraph(str(s.get("marks", "—")), styles["cell"]),
            Paragraph(str(max_marks), styles["cell"]),
            Paragraph(pct_str, styles["cell"]),
            Paragraph(s.get("status", "Absent"), styles["cell"]),
            Paragraph(s.get("time", "—"), styles["cell"])
        ])

    col_widths = [160, 80, 70, 70, 80, 80]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    doc.build(story)
    return buffer.getvalue()

def generate_test_pdf(session_code: str, stats: dict, students_data: List[dict]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = get_pdf_styles()

    story.append(Paragraph(f"🧪 Test Performance Report", styles["title"]))
    story.append(Paragraph(f"Session Code: {session_code}  |  Generated on: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}", styles["subtitle"]))
    story.append(Spacer(1, 10))

    # Stats section
    story.append(Paragraph("Class Performance Aggregates", styles["section"]))
    stats_data = [
        [Paragraph("Highest Score:", styles["stat_label"]), Paragraph(f"{stats.get('highest', 0)} pts", styles["stat_val"]),
         Paragraph("Lowest Score:", styles["stat_label"]), Paragraph(f"{stats.get('lowest', 0)} pts", styles["stat_val"])],
        [Paragraph("Average Score:", styles["stat_label"]), Paragraph(f"{stats.get('average', 0)} pts", styles["stat_val"]),
         Paragraph("Pass Percentage:", styles["stat_label"]), Paragraph(f"{stats.get('pass_pct', 0)}%", styles["stat_val"])]
    ]
    t_stats = Table(stats_data, colWidths=[110, 160, 110, 160])
    t_stats.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 15))

    story.append(Paragraph("Student Test Scoresheet", styles["section"]))
    headers = [
        Paragraph("Rank", styles["header"]),
        Paragraph("Student", styles["header"]),
        Paragraph("Score", styles["header"]),
        Paragraph("Total Marks", styles["header"]),
        Paragraph("Percentage", styles["header"]),
        Paragraph("Correct", styles["header"]),
        Paragraph("Wrong", styles["header"]),
        Paragraph("Time Taken", styles["header"])
    ]
    table_data = [headers]
    for s in students_data:
        table_data.append([
            Paragraph(str(s.get("rank", "—")), styles["cell_bold"]),
            Paragraph(s.get("name", "Student"), styles["cell_bold"]),
            Paragraph(str(s.get("score", 0)), styles["cell"]),
            Paragraph(str(s.get("total_marks", 0)), styles["cell"]),
            Paragraph(f"{s.get('percentage', 0)}%", styles["cell"]),
            Paragraph(str(s.get("correct", 0)), styles["cell"]),
            Paragraph(str(s.get("wrong", 0)), styles["cell"]),
            Paragraph(s.get("time_taken", "—"), styles["cell"])
        ])

    col_widths = [40, 150, 50, 65, 65, 50, 50, 70]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    doc.build(story)
    return buffer.getvalue()

def generate_coding_pdf(session_code: str, coding_task: dict, students_data: List[dict]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = get_pdf_styles()

    story.append(Paragraph(f"💻 Coding Assessment Report", styles["title"]))
    desc = coding_task.get("question", "Coding Assessment")
    story.append(Paragraph(f"Session Code: {session_code}  |  Language: {coding_task.get('language', 'python')}", styles["subtitle"]))
    story.append(Paragraph(f"<b>Challenge:</b> {desc}", styles["subtitle"]))
    story.append(Spacer(1, 10))

    headers = [
        Paragraph("Student", styles["header"]),
        Paragraph("Passed Cases", styles["header"]),
        Paragraph("Total Cases", styles["header"]),
        Paragraph("Score", styles["header"]),
        Paragraph("Language", styles["header"]),
        Paragraph("Submission Time", styles["header"])
    ]
    table_data = [headers]
    for s in students_data:
        table_data.append([
            Paragraph(s.get("name", "Student"), styles["cell_bold"]),
            Paragraph(str(s.get("passed_cases", 0)), styles["cell"]),
            Paragraph(str(s.get("total_cases", 0)), styles["cell"]),
            Paragraph(f"{s.get('score', 0)}%", styles["cell_bold"]),
            Paragraph(s.get("language", "—"), styles["cell"]),
            Paragraph(s.get("time", "—"), styles["cell"])
        ])

    col_widths = [160, 75, 75, 60, 70, 100]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    doc.build(story)
    return buffer.getvalue()

def generate_excel_file(headers: List[str], rows: List[List]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()

def generate_csv_file(headers: List[str], rows: List[List]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(headers)
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')

def generate_zip_archive(students_data: List[dict]) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for s in students_data:
            if s.get("coding_submitted") and s.get("coding_code"):
                name = s.get("name", "Student").replace(" ", "_")
                sid = s.get("student_id", "id")
                lang = s.get("coding_language", "python").strip().lower()
                ext = "py"
                if "js" in lang or "javascript" in lang:
                    ext = "js"
                elif "cpp" in lang or "c++" in lang:
                    ext = "cpp"
                elif "java" in lang:
                    ext = "java"
                
                filename = f"{name}_{sid}.{ext}"
                zip_file.writestr(filename, s.get("coding_code"))
    return zip_buffer.getvalue()


def generate_student_test_pdf(session_code: str, student_name: str, roll_no: str, class_name: str, test_report: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = get_pdf_styles()

    # Title & Header
    story.append(Paragraph(f"🧪 Premium Test Report Card", styles["title"]))
    date_str = datetime.fromtimestamp(test_report.get("submitted_at", time.time())).strftime('%d %B %Y')
    story.append(Paragraph(f"Session: {test_report.get('session_name') or session_code}  |  Date: {date_str}", styles["subtitle"]))
    story.append(Spacer(1, 10))

    # Student details table
    story.append(Paragraph("Student Performance Details", styles["section"]))
    stats_data = [
        [Paragraph("Student Name:", styles["stat_label"]), Paragraph(student_name, styles["stat_val"]),
         Paragraph("Roll No:", styles["stat_label"]), Paragraph(roll_no or "—", styles["stat_val"])],
        [Paragraph("Class Name:", styles["stat_label"]), Paragraph(class_name or "—", styles["stat_val"]),
         Paragraph("Rank / Total:", styles["stat_label"]), Paragraph(f"{test_report.get('rank', '—')} / {test_report.get('total_participants', '—')}", styles["stat_val"])],
        [Paragraph("Marks Earned:", styles["stat_label"]), Paragraph(f"{test_report.get('score', 0)} / {test_report.get('max_score', 0)}", styles["stat_val"]),
         Paragraph("Accuracy:", styles["stat_label"]), Paragraph(f"{test_report.get('percentage', 0)}%", styles["stat_val"])],
        [Paragraph("Time Taken:", styles["stat_label"]), Paragraph(f"{round(test_report.get('time_taken', 0) / 60)} min" if test_report.get("time_taken") else "—", styles["stat_val"]),
         Paragraph("Status:", styles["stat_label"]), Paragraph("Completed", styles["stat_val"])]
    ]
    t_stats = Table(stats_data, colWidths=[110, 160, 110, 160])
    t_stats.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 15))

    # Questions Breakdown
    story.append(Paragraph("Question Breakdown", styles["section"]))
    headers = [
        Paragraph("Q#", styles["header"]),
        Paragraph("Topic", styles["header"]),
        Paragraph("Question", styles["header"]),
        Paragraph("Your Answer", styles["header"]),
        Paragraph("Correct Answer", styles["header"]),
        Paragraph("Status", styles["header"]),
        Paragraph("Marks", styles["header"])
    ]
    table_data = [headers]
    for i, q in enumerate(test_report.get("questions", [])):
        status_str = "Correct" if q.get("is_correct") else ("Pending" if q.get("evaluation_status") == "pending" else "Incorrect")
        table_data.append([
            Paragraph(str(i + 1), styles["cell_bold"]),
            Paragraph(q.get("topic", "General"), styles["cell"]),
            Paragraph(q.get("question", ""), styles["cell"]),
            Paragraph(str(q.get("student_answer") or "—"), styles["cell"]),
            Paragraph(str(q.get("correct_answer") or "—"), styles["cell"]),
            Paragraph(status_str, styles["cell_bold"]),
            Paragraph(f"{q.get('marks_earned', 0)}/{q.get('max_marks', 0)}", styles["cell"])
        ])

    col_widths = [30, 70, 170, 80, 80, 60, 50]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # Teacher Remarks / Suggestions
    story.append(Spacer(1, 15))
    story.append(Paragraph("Feedback & Suggestions", styles["section"]))
    
    feedback_text = ""
    for q in test_report.get("questions", []):
        if q.get("teacher_feedback"):
            feedback_text += f"<b>Q:</b> {q.get('question', '')[:50]}...<br/><b>Feedback:</b> {q.get('teacher_feedback')}<br/><br/>"
            
    if not feedback_text:
        pct = test_report.get("percentage", 0)
        feedback_text = (
            "Excellent performance! Keep up the great work and aim even higher." if pct >= 80 else
            "Good effort! Focus on the topics you missed to improve your score." if pct >= 60 else
            "Keep practicing! Review the incorrect answers and strengthen your concepts."
        )
    story.append(Paragraph(feedback_text, styles["stat_val"]))

    doc.build(story)
    return buffer.getvalue()


def generate_student_tasks_pdf(session_code: str, student_name: str, roll_no: str, class_name: str, task_reports: List[dict]) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = []
    styles = get_pdf_styles()

    # Title & Header
    story.append(Paragraph(f"📋 Task Performance Report", styles["title"]))
    story.append(Paragraph(f"Session: {task_reports[0].get('session_name') or session_code}  |  Date: {datetime.now().strftime('%d %B %Y')}", styles["subtitle"]))
    story.append(Spacer(1, 10))

    # Student details table
    story.append(Paragraph("Student Details", styles["section"]))
    stats_data = [
        [Paragraph("Student Name:", styles["stat_label"]), Paragraph(student_name, styles["stat_val"]),
         Paragraph("Roll No:", styles["stat_label"]), Paragraph(roll_no or "—", styles["stat_val"])],
        [Paragraph("Class Name:", styles["stat_label"]), Paragraph(class_name or "—", styles["stat_val"]),
         Paragraph("Total Tasks:", styles["stat_label"]), Paragraph(str(len(task_reports)), styles["stat_val"])]
    ]
    t_stats = Table(stats_data, colWidths=[110, 160, 110, 160])
    t_stats.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_stats)
    story.append(Spacer(1, 15))

    # Tasks table
    story.append(Paragraph("Task Submission Log", styles["section"]))
    headers = [
        Paragraph("Task#", styles["header"]),
        Paragraph("Topic", styles["header"]),
        Paragraph("Question", styles["header"]),
        Paragraph("Your Answer", styles["header"]),
        Paragraph("Status", styles["header"]),
        Paragraph("Score", styles["header"])
    ]
    table_data = [headers]
    for i, rpt in enumerate(task_reports):
        q = rpt.get("questions", [{}])[0]
        status_str = q.get("evaluation_status", "approved").capitalize()
        if q.get("evaluation_status") == "approved":
            status_str = "Correct" if q.get("is_correct") else "Incorrect"
        table_data.append([
            Paragraph(str(i + 1), styles["cell_bold"]),
            Paragraph(q.get("topic", "General"), styles["cell"]),
            Paragraph(q.get("question", ""), styles["cell"]),
            Paragraph(str(q.get("student_answer") or "—"), styles["cell"]),
            Paragraph(status_str, styles["cell_bold"]),
            Paragraph(f"{q.get('marks_earned', 0)}/{q.get('max_marks', 0)}", styles["cell"])
        ])

    col_widths = [45, 75, 200, 100, 70, 50]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # Feedback section
    feedback_text = ""
    for i, rpt in enumerate(task_reports):
        q = rpt.get("questions", [{}])[0]
        if q.get("teacher_feedback"):
            feedback_text += f"<b>Task #{i+1}:</b> {q.get('teacher_feedback')}<br/>"
    if feedback_text:
        story.append(Spacer(1, 15))
        story.append(Paragraph("Teacher Feedback", styles["section"]))
        story.append(Paragraph(feedback_text, styles["stat_val"]))

    doc.build(story)
    return buffer.getvalue()

