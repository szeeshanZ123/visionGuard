"""
VisionGuard AI - Inspection Reports, PDF Export, and Data Export Module (Phase 4.5).

Provides report data generation, server-side filter validation,
Excel-compatible CSV generation (UTF-8 BOM), and professional printable PDF generation (ReportLab).
Strictly separates AI estimates from user-entered maintenance data and avoids leaking local file paths.
"""

import io
import csv
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

from database.db import (
    get_inspections,
    get_inspection_activity,
    ALLOWED_STATUSES,
    DEFAULT_DB_PATH,
    compute_maintenance_status,
)


# Standard Civil Engineering & AI Safety Disclaimer
REPORT_DISCLAIMER_TEXT = (
    "Civil Engineering & Safety Disclaimer: VisionGuard AI detections represent 2D computer vision "
    "statistical inferences. Confidence scores indicate visual model likelihood, not physical pavement "
    "failure severity, cavity depth, or roadway load capacity. Pixel bounding boxes do not measure millimeter "
    "crack width without physical ground-plane calibration. Workflow statuses and target repair dates are "
    "administrative records entered by personnel and do not certify that physical roadway engineering repairs "
    "have occurred."
)

ALLOWED_DEADLINE_FILTERS = [
    "all",
    "overdue",
    "due_today",
    "upcoming",
    "resolved",
    "no_deadline",
    "none",
]


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that accumulates pages and renders total page numbers
    along with running header and civil engineering footer on every page.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, page_count: int):
        self.saveState()

        # Page dimensions: landscape letter = 792 x 612
        page_w = 792
        page_h = 612
        left_m = 36
        right_m = 36
        content_w = page_w - left_m - right_m

        # 1. Running Header (omitted on page 1 for clean title block)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#0f172a"))
            self.drawString(left_m, page_h - 26, "VisionGuard AI • Infrastructure Defect & Remediation Report")

            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748b"))
            self.drawRightString(page_w - right_m, page_h - 26, f"Generated: {datetime.date.today().isoformat()}")

            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.75)
            self.line(left_m, page_h - 30, page_w - right_m, page_h - 30)

        # 2. Running Footer
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(left_m, 32, page_w - right_m, 32)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor("#64748b"))
        disclaimer_short = "Notice: AI detections measure statistical model likelihood, not physical roadway load capacity or structural safety."
        self.drawString(left_m, 20, disclaimer_short)

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(page_w - right_m, 20, page_str)

        self.restoreState()


def validate_report_filters(filters: Optional[Dict[str, Any]] = None) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Validates server-side report filters to ensure type safety and prevent malformed inputs.
    Returns (is_valid, normalized_filters, error_message).
    """
    raw = filters or {}
    norm: Dict[str, Any] = {}

    # 1. Date Range: start_date & end_date
    start_date = raw.get("start_date")
    if start_date is not None and str(start_date).strip() != "":
        s_str = str(start_date).strip()[:10]
        try:
            s_parsed = datetime.datetime.strptime(s_str, "%Y-%m-%d").date()
            norm["start_date"] = s_parsed.isoformat()
        except ValueError:
            return False, {}, f"Invalid start_date '{start_date}'. Must be in YYYY-MM-DD format."
    else:
        norm["start_date"] = None

    end_date = raw.get("end_date")
    if end_date is not None and str(end_date).strip() != "":
        e_str = str(end_date).strip()[:10]
        try:
            e_parsed = datetime.datetime.strptime(e_str, "%Y-%m-%d").date()
            norm["end_date"] = e_parsed.isoformat()
        except ValueError:
            return False, {}, f"Invalid end_date '{end_date}'. Must be in YYYY-MM-DD format."
    else:
        norm["end_date"] = None

    if norm["start_date"] and norm["end_date"]:
        if norm["start_date"] > norm["end_date"]:
            return False, {}, f"Invalid date range: start_date ({norm['start_date']}) cannot be after end_date ({norm['end_date']})."

    # 2. Defect Category
    cat = raw.get("category")
    if cat and str(cat).strip() and str(cat).strip().lower() != "all":
        norm["category"] = str(cat).strip()
    else:
        norm["category"] = None

    # 3. Status
    status = raw.get("status")
    if status and str(status).strip() and str(status).strip().lower() != "all":
        st_clean = str(status).strip()
        if st_clean not in ALLOWED_STATUSES and st_clean.lower() not in ["in progress group", "in-progress", "active"]:
            return False, {}, f"Invalid status '{status}'. Must be one of: {ALLOWED_STATUSES} or 'all'."
        norm["status"] = st_clean
    else:
        norm["status"] = None

    # 4. Maintenance Deadline
    deadline = raw.get("deadline") or raw.get("deadline_filter") or raw.get("urgency")
    if deadline and str(deadline).strip() and str(deadline).strip().lower() != "all":
        dl_clean = str(deadline).strip().lower()
        if dl_clean not in ALLOWED_DEADLINE_FILTERS:
            return False, {}, f"Invalid deadline filter '{deadline}'. Must be one of: {ALLOWED_DEADLINE_FILTERS}."
        norm["deadline"] = dl_clean
    else:
        norm["deadline"] = None

    # 5. City and Area
    city = raw.get("city")
    if city and str(city).strip() and str(city).strip().lower() != "all":
        norm["city"] = str(city).strip()[:100]
    else:
        norm["city"] = None

    area = raw.get("area")
    if area and str(area).strip() and str(area).strip().lower() != "all":
        norm["area"] = str(area).strip()[:100]
    else:
        norm["area"] = None

    # 6. Keyword Search
    q = raw.get("q") or raw.get("search") or raw.get("search_query")
    if q and str(q).strip():
        norm["search_query"] = str(q).strip()[:200]
    else:
        norm["search_query"] = None

    # 7. Limits & Offsets
    try:
        norm["limit"] = min(1000, max(1, int(raw.get("limit", 500))))
    except (ValueError, TypeError):
        norm["limit"] = 500

    try:
        norm["offset"] = max(0, int(raw.get("offset", 0)))
    except (ValueError, TypeError):
        norm["offset"] = 0

    return True, norm, None


def sanitize_inspection_for_report(rec: Dict[str, Any], latest_activity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Sanitizes an inspection record for public report output.
    Never exposes internal server filesystem paths.
    Provides clear boundaries between AI estimates, user inputs, and location data.
    """
    record_id = rec.get("id")
    lat = rec.get("latitude")
    lon = rec.get("longitude")
    has_coords = lat is not None and lon is not None

    if has_coords:
        coords_display = f"{lat:.5f}°, {lon:.5f}°"
    else:
        coords_display = "Not recorded"

    # AI detection metrics
    defect_count = int(rec.get("defect_count", 0))
    top_conf = rec.get("confidence")
    if top_conf is not None and defect_count > 0:
        try:
            top_conf_pct = f"{float(top_conf) * 100:.1f}%"
        except (ValueError, TypeError):
            top_conf_pct = "N/A"
    else:
        top_conf_pct = "N/A" if defect_count > 0 else "0.0%"

    # Activity formatting
    if latest_activity:
        act_action = latest_activity.get("action_type") or "updated"
        act_time = str(latest_activity.get("created_at") or "")[:10]
        act_notes = (latest_activity.get("notes") or "").strip()
        act_display = f"{act_action.replace('_', ' ').title()} ({act_time})" if act_time else act_action
        if act_notes:
            act_display += f" - {act_notes}"
    else:
        act_display = "Initial record created"

    return {
        "id": record_id,
        "image_name": rec.get("image_name") or f"inspection_{record_id}.jpg",
        "uploaded_at": str(rec.get("uploaded_at") or ""),
        "annotated_image_url": f"/api/inspections/{record_id}/image/annotated",
        "original_image_url": f"/api/inspections/{record_id}/image/original",
        # Spatial / Location (Field entered)
        "road_name": rec.get("road_name") or "",
        "area": rec.get("area") or "",
        "city": rec.get("city") or "",
        "latitude": lat,
        "longitude": lon,
        "has_coords": has_coords,
        "coords_display": coords_display,
        "location_notes": rec.get("location_notes") or rec.get("notes") or "",
        # AI Computer Vision Estimates (Authentic Model Outputs)
        "defect_count": defect_count,
        "defect_type": rec.get("defect_type") or ("None detected" if defect_count == 0 else "Distress"),
        "confidence": top_conf,
        "confidence_pct": top_conf_pct,
        "confidence_threshold": rec.get("confidence_threshold", 0.25),
        "inspection_mode": rec.get("inspection_mode", "standard"),
        "detections": rec.get("detections", []),
        # Maintenance & Remediation Workflow (User / Administrative Inputs)
        "status": rec.get("status") or "Open",
        "target_repair_date": rec.get("target_repair_date"),
        "maintenance_urgency": rec.get("maintenance_urgency") or "none",
        "maintenance_label": rec.get("maintenance_label") or "No Target Date",
        "is_overdue": bool(rec.get("is_overdue", False)),
        "days_remaining": rec.get("days_remaining"),
        # Audit Trail
        "latest_activity": act_display,
    }


def generate_report_data(
    filters: Optional[Dict[str, Any]] = None,
    ref_date: Optional[datetime.date] = None,
    db_path: str = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Queries SQLite database according to validated filters and builds
    the full data structure for preview, PDF export, and CSV export.
    """
    is_valid, norm_filters, err_msg = validate_report_filters(filters)
    if not is_valid:
        raise ValueError(err_msg or "Invalid report filters")

    ref_d = ref_date or datetime.date.today()

    # Query records matching filters
    records = get_inspections(
        status=norm_filters.get("status"),
        limit=norm_filters.get("limit", 500),
        offset=norm_filters.get("offset", 0),
        category=norm_filters.get("category"),
        search_query=norm_filters.get("search_query"),
        deadline_filter=norm_filters.get("deadline"),
        start_date=norm_filters.get("start_date"),
        end_date=norm_filters.get("end_date"),
        city=norm_filters.get("city"),
        area=norm_filters.get("area"),
        ref_date=ref_d,
        db_path=db_path
    )

    # Process and sanitize each record, attaching latest audit activity
    sanitized_records: List[Dict[str, Any]] = []
    category_counts = {
        "Longitudinal Crack": 0,
        "Transverse Crack": 0,
        "Alligator Crack": 0,
        "Pothole": 0,
        "Sound Surface": 0,
    }
    status_counts = {
        "Open": 0,
        "Under Review": 0,
        "Repair in Progress": 0,
        "Resolved": 0,
    }
    urgency_counts = {
        "overdue": 0,
        "due_today": 0,
        "upcoming": 0,
        "resolved": 0,
        "none": 0,
    }

    total_defects = 0

    for rec in records:
        # Load activity log to find latest activity
        rec_id = rec["id"]
        try:
            acts = get_inspection_activity(rec_id, db_path=db_path)
            latest_act = acts[-1] if acts else None
        except Exception:
            latest_act = None

        s_rec = sanitize_inspection_for_report(rec, latest_activity=latest_act)
        sanitized_records.append(s_rec)

        # Aggregate defects
        cnt = s_rec["defect_count"]
        total_defects += cnt
        if cnt == 0:
            category_counts["Sound Surface"] += 1
        else:
            # Check individual detections if present
            dets = s_rec.get("detections") or []
            if dets:
                for d in dets:
                    cat_name = (d.get("distress_category") or d.get("class_name") or "").lower()
                    if "longitudinal" in cat_name or "d00" in cat_name:
                        category_counts["Longitudinal Crack"] += 1
                    elif "transverse" in cat_name or "d10" in cat_name:
                        category_counts["Transverse Crack"] += 1
                    elif "alligator" in cat_name or "d20" in cat_name:
                        category_counts["Alligator Crack"] += 1
                    elif "pothole" in cat_name or "d40" in cat_name:
                        category_counts["Pothole"] += 1
            else:
                dt_str = (s_rec.get("defect_type") or "").lower()
                if "longitudinal" in dt_str:
                    category_counts["Longitudinal Crack"] += 1
                if "transverse" in dt_str:
                    category_counts["Transverse Crack"] += 1
                if "alligator" in dt_str:
                    category_counts["Alligator Crack"] += 1
                if "pothole" in dt_str:
                    category_counts["Pothole"] += 1

        # Status distribution
        st = s_rec["status"]
        if st in status_counts:
            status_counts[st] += 1
        else:
            status_counts["Open"] += 1

        # Urgency distribution
        urg = s_rec["maintenance_urgency"]
        if urg in urgency_counts:
            urgency_counts[urg] += 1
        else:
            urgency_counts["none"] += 1

    total_inspections = len(sanitized_records)
    active_unresolved = status_counts["Open"] + status_counts["Under Review"] + status_counts["Repair in Progress"]

    return {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reference_date": ref_d.isoformat(),
        "applied_filters": norm_filters,
        "summary": {
            "total_inspections": total_inspections,
            "total_defects": total_defects,
            "active_unresolved": active_unresolved,
            "resolved_count": status_counts["Resolved"],
            "status_distribution": status_counts,
            "category_distribution": category_counts,
            "deadline_distribution": urgency_counts,
            "overdue_count": urgency_counts["overdue"],
            "due_today_count": urgency_counts["due_today"],
            "upcoming_count": urgency_counts["upcoming"],
            "no_deadline_count": urgency_counts["none"],
        },
        "records": sanitized_records,
        "disclaimer": REPORT_DISCLAIMER_TEXT,
    }


def generate_report_csv(report_data: Dict[str, Any]) -> str:
    """
    Generates a structured, Excel-friendly CSV export with UTF-8 BOM.
    Contains summary metadata followed by itemized inspection rows.
    """
    buf = io.StringIO()
    # Write UTF-8 Byte Order Mark for Microsoft Excel compatibility
    buf.write("\ufeff")

    writer = csv.writer(buf, lineterminator="\r\n")

    # Header metadata comments
    writer.writerow(["# VisionGuard AI - Road Defect Inspection & Remediation Report"])
    writer.writerow([f"# Generated At: {report_data.get('generated_at', '')}"])
    filters = report_data.get("applied_filters", {})
    writer.writerow([
        f"# Filters: Start Date: {filters.get('start_date') or 'All'} | End Date: {filters.get('end_date') or 'All'} | "
        f"Category: {filters.get('category') or 'All'} | Status: {filters.get('status') or 'All'} | "
        f"Deadline: {filters.get('deadline') or 'All'} | City: {filters.get('city') or 'All'} | Area: {filters.get('area') or 'All'}"
    ])
    summary = report_data.get("summary", {})
    writer.writerow([
        f"# Total Matching Inspections: {summary.get('total_inspections', 0)} | "
        f"Total Detected Defects: {summary.get('total_defects', 0)} | "
        f"Active Unresolved: {summary.get('active_unresolved', 0)} | "
        f"Overdue Repairs: {summary.get('overdue_count', 0)}"
    ])
    writer.writerow(["# Notice: AI detections measure statistical likelihood; statuses and deadlines are user/field updates."])
    writer.writerow([])  # Empty separator row

    # Column Headers
    writer.writerow([
        "Inspection ID",
        "Inspection Date",
        "Workflow Status (User Entry)",
        "Maintenance Urgency",
        "Target Repair Date",
        "Days Remaining",
        "Road Name",
        "Area",
        "City",
        "Latitude (GPS)",
        "Longitude (GPS)",
        "Defect Count (AI Estimated)",
        "Distress Categories (AI Estimated)",
        "Top Confidence % (AI Estimated)",
        "Inspection Mode",
        "Location Notes / Observations",
        "Latest Audit Activity",
    ])

    records = report_data.get("records", [])
    if not records:
        writer.writerow(["No inspection records match the specified filters."])
        return buf.getvalue()

    for r in records:
        lat = f"{r['latitude']:.6f}" if r.get("latitude") is not None else ""
        lon = f"{r['longitude']:.6f}" if r.get("longitude") is not None else ""
        days_rem = r.get("days_remaining")
        days_str = str(days_rem) if days_rem is not None else ""

        # Clean location notes of raw newlines so Excel displays neatly
        notes_clean = " ".join((r.get("location_notes") or "").split())

        writer.writerow([
            r.get("id"),
            r.get("uploaded_at"),
            r.get("status"),
            r.get("maintenance_label"),
            r.get("target_repair_date") or "",
            days_str,
            r.get("road_name") or "",
            r.get("area") or "",
            r.get("city") or "",
            lat,
            lon,
            r.get("defect_count", 0),
            r.get("defect_type") or "",
            r.get("confidence_pct") or "N/A",
            r.get("inspection_mode") or "standard",
            notes_clean,
            r.get("latest_activity") or "",
        ])

    return buf.getvalue()


def generate_report_pdf(report_data: Dict[str, Any]) -> bytes:
    """
    Renders an executive-grade, printable PDF inspection report using ReportLab.
    Format: Landscape Letter (11 x 8.5 in) with running headers, footers, KPI cards,
    distress distributions, and itemized records.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=42,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    brand_style = ParagraphStyle(
        "BrandHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "BrandSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"),
    )
    filter_box_style = ParagraphStyle(
        "FilterMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#334155"),
    )
    sec_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=8,
        spaceAfter=4,
    )
    th_style = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
        alignment=0,
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    cell_bold_style = ParagraphStyle(
        "TableCellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )
    disclaimer_p_style = ParagraphStyle(
        "DisclaimerP",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9.5,
        textColor=colors.HexColor("#475569"),
    )

    story = []

    # 1. Header Banner & Title Block
    header_table_data = [
        [
            Paragraph("🛡️ <b>VisionGuard AI</b> • Infrastructure Defect & Remediation Report", brand_style),
            Paragraph(
                f"<b>Report Date:</b> {report_data.get('generated_at', '')}<br/>"
                f"<b>Reference Date:</b> {report_data.get('reference_date', '')}",
                subtitle_style
            ),
        ]
    ]
    header_table = Table(header_table_data, colWidths=[490, 230])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)

    # 2. Applied Filters Summary Bar
    filters = report_data.get("applied_filters", {})
    date_range_str = (
        f"{filters.get('start_date') or 'Beginning'} to {filters.get('end_date') or 'Present'}"
        if (filters.get("start_date") or filters.get("end_date"))
        else "All Available Dates"
    )
    cat_str = filters.get("category") or "All Categories"
    status_str = filters.get("status") or "All Statuses"
    deadline_str = (filters.get("deadline") or "All Deadlines").replace("_", " ").title()
    loc_str = ", ".join(filter(Boolean, [filters.get("city"), filters.get("area")])) or "All Locations"

    filter_text = (
        f"<b>Applied Filters:</b> Date Range: <i>{date_range_str}</i> | "
        f"Category: <i>{cat_str}</i> | Status: <i>{status_str}</i> | "
        f"Deadline: <i>{deadline_str}</i> | Location: <i>{loc_str}</i>"
    )
    filter_box = Table([[Paragraph(filter_text, filter_box_style)]], colWidths=[720])
    filter_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(filter_box)
    story.append(Spacer(1, 8))

    # 3. KPI Metric Summary Cards (4 Cards across 720 pt = 180 pt each)
    summary = report_data.get("summary", {})
    total_insp = summary.get("total_inspections", 0)
    total_def = summary.get("total_defects", 0)
    active_unres = summary.get("active_unresolved", 0)
    overdue_cnt = summary.get("overdue_count", 0)

    def make_kpi_cell(label: str, val: str, caption: str, val_color: str):
        return [
            Paragraph(f"<font color='#64748b' size=7><b>{label.upper()}</b></font>", styles["Normal"]),
            Paragraph(f"<font color='{val_color}' size=16><b>{val}</b></font>", styles["Normal"]),
            Paragraph(f"<font color='#94a3b8' size=6.5>{caption}</font>", styles["Normal"]),
        ]

    kpi_card_1 = make_kpi_cell("Total Inspections", str(total_insp), "Matching filter criteria", "#0f172a")
    kpi_card_2 = make_kpi_cell("Detected Defects", str(total_def), "Cracks & potholes found", "#dc2626")
    kpi_card_3 = make_kpi_cell("Active Work Orders", str(active_unres), "Open / Repair in progress", "#d97706")
    kpi_card_4 = make_kpi_cell("Overdue Remediation", str(overdue_cnt), "Past target repair date", "#b91c1c")

    kpi_matrix = [
        [kpi_card_1[0], kpi_card_2[0], kpi_card_3[0], kpi_card_4[0]],
        [kpi_card_1[1], kpi_card_2[1], kpi_card_3[1], kpi_card_4[1]],
        [kpi_card_1[2], kpi_card_2[2], kpi_card_3[2], kpi_card_4[2]],
    ]
    kpi_table = Table(kpi_matrix, colWidths=[180, 180, 180, 180])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#fef2f2")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#fffbeb")),
        ("BACKGROUND", (3, 0), (3, -1), colors.HexColor("#fef2f2")),
        ("BOX", (0, 0), (0, -1), 0.75, colors.HexColor("#cbd5e1")),
        ("BOX", (1, 0), (1, -1), 0.75, colors.HexColor("#fecaca")),
        ("BOX", (2, 0), (2, -1), 0.75, colors.HexColor("#fde68a")),
        ("BOX", (3, 0), (3, -1), 0.75, colors.HexColor("#fca5a5")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 8))

    # 4. Distress Categories & Workflow Distribution Summary
    cat_dist = summary.get("category_distribution", {})
    status_dist = summary.get("status_distribution", {})
    urgency_dist = summary.get("deadline_distribution", {})

    cat_table_rows = [
        [
            Paragraph("<b>Distress Category</b>", th_style),
            Paragraph("<b>Detected Count</b>", th_style),
            Paragraph("<b>Distribution %</b>", th_style),
        ]
    ]
    for cname in ["Longitudinal Crack", "Transverse Crack", "Alligator Crack", "Pothole", "Sound Surface"]:
        c_count = cat_dist.get(cname, 0)
        c_pct = f"{(c_count / total_def * 100):.1f}%" if total_def > 0 and cname != "Sound Surface" else (
            f"{(c_count / total_insp * 100):.1f}%" if total_insp > 0 and cname == "Sound Surface" else "0.0%"
        )
        cat_table_rows.append([
            Paragraph(cname, cell_style),
            Paragraph(str(c_count), cell_bold_style),
            Paragraph(c_pct, cell_style),
        ])

    maint_table_rows = [
        [
            Paragraph("<b>Workflow & Compliance State</b>", th_style),
            Paragraph("<b>Record Count</b>", th_style),
            Paragraph("<b>Operational Description</b>", th_style),
        ],
        [
            Paragraph("Open Records", cell_style),
            Paragraph(str(status_dist.get("Open", 0)), cell_bold_style),
            Paragraph("Awaiting technical triage", cell_style),
        ],
        [
            Paragraph("Repair in Progress / Review", cell_style),
            Paragraph(str(status_dist.get("Repair in Progress", 0) + status_dist.get("Under Review", 0)), cell_bold_style),
            Paragraph("Active remediation work order", cell_style),
        ],
        [
            Paragraph("Resolved Records", cell_style),
            Paragraph(str(status_dist.get("Resolved", 0)), cell_bold_style),
            Paragraph("Closed workflow state", cell_style),
        ],
        [
            Paragraph("Overdue Maintenance", cell_style),
            Paragraph(f"<font color='#dc2626'><b>{urgency_dist.get('overdue', 0)}</b></font>", cell_style),
            Paragraph("Target repair date has expired", cell_style),
        ],
        [
            Paragraph("Due Today / Upcoming", cell_style),
            Paragraph(str(urgency_dist.get("due_today", 0) + urgency_dist.get("upcoming", 0)), cell_bold_style),
            Paragraph("Scheduled remediation timeline", cell_style),
        ],
    ]

    t_cat = Table(cat_table_rows, colWidths=[160, 95, 95])
    t_cat.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))

    t_maint = Table(maint_table_rows, colWidths=[150, 75, 125])
    t_maint.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 3),
    ]))

    side_by_side = Table([
        [
            Paragraph("<b>Defect Category Breakdown</b>", sec_title_style),
            Paragraph("<b>Workflow & Maintenance Status</b>", sec_title_style)
        ],
        [t_cat, t_maint]
    ], colWidths=[360, 360])
    side_by_side.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(side_by_side)
    story.append(Spacer(1, 10))

    # 5. Itemized Inspection Registry Table
    story.append(Paragraph("<b>Itemized Road Inspection Records</b>", sec_title_style))

    # Column widths summing to 720 pt:
    # ID: 32, Date: 65, Location: 110, GPS: 75, Defect Count: 40, Categories: 105, Conf: 45, Status: 75, Target/Urgency: 88, Activity: 85 = 720 pt
    col_w = [32, 65, 110, 75, 40, 105, 45, 75, 88, 85]

    rec_table_rows = [
        [
            Paragraph("<b>#</b>", th_style),
            Paragraph("<b>Date</b>", th_style),
            Paragraph("<b>Location / Road</b>", th_style),
            Paragraph("<b>GPS Coords</b>", th_style),
            Paragraph("<b>Defects</b>", th_style),
            Paragraph("<b>Categories</b>", th_style),
            Paragraph("<b>AI Conf.</b>", th_style),
            Paragraph("<b>Status</b>", th_style),
            Paragraph("<b>Target Date</b>", th_style),
            Paragraph("<b>Latest Audit</b>", th_style),
        ]
    ]

    records = report_data.get("records", [])
    if not records:
        empty_callout = Table([
            [Paragraph("<b>No inspection records matched the specified filter criteria.</b>", cell_bold_style)],
            [Paragraph("Try adjusting your date range, broadening categories, or resetting the deadline filter.", cell_style)]
        ], colWidths=[720])
        empty_callout.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("PADDING", (0, 0), (-1, -1), 15),
        ]))
        story.append(empty_callout)
    else:
        for idx, r in enumerate(records):
            # Location text
            loc_parts = []
            if r.get("road_name"):
                loc_parts.append(f"<b>{r['road_name']}</b>")
            sub_loc = ", ".join(filter(Boolean, [r.get("area"), r.get("city")]))
            if sub_loc:
                loc_parts.append(sub_loc)
            loc_html = "<br/>".join(loc_parts) if loc_parts else "<i>Not specified</i>"

            # Date text
            date_str = str(r.get("uploaded_at") or "")[:10]

            # GPS
            gps_html = f"<code>{r['coords_display']}</code>" if r.get("has_coords") else "<font color='#94a3b8'>None</font>"

            # Defects & categories
            d_count = r.get("defect_count", 0)
            d_count_html = f"<b>{d_count}</b>" if d_count > 0 else "<font color='#16a34a'>0</font>"
            d_cat = r.get("defect_type") or "Sound Surface"

            # Confidence
            conf_str = r.get("confidence_pct", "N/A")

            # Status styling
            st_val = r.get("status") or "Open"
            if st_val == "Resolved":
                st_color = "#16a34a"
            elif st_val in ["Repair in Progress", "Under Review"]:
                st_color = "#d97706"
            else:
                st_color = "#2563eb"
            st_html = f"<font color='{st_color}'><b>{st_val}</b></font>"

            # Deadline styling
            tr_date = r.get("target_repair_date") or ""
            urg_label = r.get("maintenance_label") or "No Target Date"
            if r.get("is_overdue"):
                dl_html = f"<font color='#dc2626'><b>{tr_date}</b><br/>{urg_label}</font>"
            elif r.get("maintenance_urgency") == "due_today":
                dl_html = f"<font color='#d97706'><b>{tr_date}</b><br/>Due Today</font>"
            elif tr_date:
                dl_html = f"<b>{tr_date}</b><br/><font color='#64748b'>{urg_label}</font>"
            else:
                dl_html = "<font color='#94a3b8'>No Date</font>"

            # Audit history summary
            act_summary = r.get("latest_activity") or "Created"

            bg_color = colors.HexColor("#ffffff") if idx % 2 == 0 else colors.HexColor("#f8fafc")

            rec_table_rows.append([
                Paragraph(str(r["id"]), cell_bold_style),
                Paragraph(date_str, cell_style),
                Paragraph(loc_html, cell_style),
                Paragraph(gps_html, cell_style),
                Paragraph(d_count_html, cell_style),
                Paragraph(d_cat, cell_style),
                Paragraph(conf_str, cell_style),
                Paragraph(st_html, cell_style),
                Paragraph(dl_html, cell_style),
                Paragraph(act_summary, cell_style),
            ])

        records_table = Table(rec_table_rows, colWidths=col_w, repeatRows=1)
        records_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        # Style header text white
        for c in range(len(col_w)):
            records_table.setStyle(TableStyle([
                ("TEXTCOLOR", (c, 0), (c, 0), colors.white)
            ]))
        story.append(records_table)

    story.append(Spacer(1, 12))

    # 6. Civil Engineering Disclaimer Box
    disclaimer_box = Table([[
        Paragraph(
            "<b>Civil Engineering Notice & Safety Disclaimer:</b> " + REPORT_DISCLAIMER_TEXT,
            disclaimer_p_style
        )
    ]], colWidths=[720])
    disclaimer_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(KeepTogether(disclaimer_box))

    # Build document with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


def Boolean(val: Any) -> bool:
    """Helper for filtering non-empty strings in join."""
    return bool(val and str(val).strip())
