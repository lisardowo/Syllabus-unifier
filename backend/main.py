import re
import uuid
from ics import Calendar, Event
from fastapi import FastAPI, UploadFile, File
from typing import List
import io
try:
    import pdfplumber  # Optional, better table/positional extraction
except ImportError:  # pragma: no cover
    pdfplumber = None
app = FastAPI()
DAY_NAMES = {
    # English
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6,
    'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6,
    # Spanish
    'lunes': 0, 'martes': 1, 'miércoles': 2, 'miercoles': 2, 'jueves': 3, 'viernes': 4, 'sábado': 5, 'sabado': 5, 'domingo': 6,
    'lun': 0, 'mar': 1, 'mie': 2, 'mié': 2, 'jue': 3, 'vie': 4, 'sab': 5, 'sáb': 5, 'dom': 6,
    # Spanish 2-letter common abbreviations in schedules
    'lu': 0, 'ma': 1, 'mi': 2, 'ju': 3, 'vi': 4, 'sa': 5, 'do': 6
}

# Day token and time patterns
DAY_TOKEN = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|lun|mar|mie|mié|jue|vie|sab|sáb|dom|lu|ma|mi|ju|vi|sa|do"
# Safer inline day tokens (exclude 2-letter forms to reduce false positives like 'sa' in 'casa')
DAY_TOKEN_INLINE = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|lun|mar|mie|mié|jue|vie|sab|sáb|dom"
# Time token tightened to avoid false positives like "7-8"; require HH:MM optionally with am/pm OR H am/pm
TIME_TOKEN = r"(?:\d{1,2}:\d{2}\s*(?:am|pm|a\.m\.|p\.m\.)?|\d{1,2}\s*(?:am|pm|a\.m\.|p\.m\.))"
SCHEDULE_PATTERN = re.compile(
    rf"(?P<days>(?:\b(?:{DAY_TOKEN_INLINE})\b)(?:\s*(?:/|,|y|and|&)+\s*(?:\b(?:{DAY_TOKEN_INLINE})\b))*)\s*[:\-–—]?\s*(?P<start>{TIME_TOKEN})\s*(?:-|–|—|a|to)\s*(?P<end>{TIME_TOKEN})",
    re.IGNORECASE
)

def _strip_accents(s: str) -> str:
    return (
        s.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
         .replace('Á', 'a').replace('É', 'e').replace('Í', 'i').replace('Ó', 'o').replace('Ú', 'u')
    )

def _parse_time_24(t: str) -> str:
    t = t.strip().lower()
    t = t.replace('a.m.', 'am').replace('p.m.', 'pm')
    ampm = None
    if t.endswith('am'):
        ampm = 'am'; t = t[:-2].strip()
    elif t.endswith('pm'):
        ampm = 'pm'; t = t[:-2].strip()
    # split h and m
    if ':' in t:
        h_str, m_str = t.split(':', 1)
    else:
        h_str, m_str = t, '00'
    h = int(h_str)
    m = int(''.join(ch for ch in m_str if ch.isdigit()) or '0')
    if ampm:
        if ampm == 'am':
            if h == 12:
                h = 0
        else:  # pm
            if h != 12:
                h += 12
    return f"{h:02d}:{m:02d}"

def extract_schedule(text):
    """Extract class schedule as list of (weekday, HH:MM, HH:MM). Supports multiple days, AM/PM and line-based formats."""
    slots = []
    # Pass 1: inline patterns with days + time in the same line
    for m in SCHEDULE_PATTERN.finditer(text):
        days_raw = m.group('days')
        start_raw = m.group('start')
        end_raw = m.group('end')
        start = _parse_time_24(start_raw)
        end = _parse_time_24(end_raw)
        for day_token in re.findall(rf"\b({DAY_TOKEN_INLINE})\b", days_raw, flags=re.IGNORECASE):
            key = _strip_accents(day_token.lower())
            weekday = DAY_NAMES.get(key)
            if weekday is not None:
                slots.append((weekday, start, end))
    # Pass 2: line-based patterns, e.g., "LU" on one line, next line "13:00-14:30 T-402"
    lines = text.splitlines()
    current_days = []
    time_range = re.compile(rf"(?P<start>{TIME_TOKEN})\s*(?:-|–|—|a|to)\s*(?P<end>{TIME_TOKEN})", re.IGNORECASE)
    day_line_re = re.compile(rf"\b(?:{DAY_TOKEN})(?:\b\s*(?:/|,|\||\s+))+\b|\b(?:{DAY_TOKEN})\b\s*$", re.IGNORECASE)
    for line in lines:
        low = _strip_accents(line.lower())
        # Detect day-only lines or day groups
        found_days = re.findall(rf"\b({DAY_TOKEN})\b", low, flags=re.IGNORECASE)
        found_times = list(time_range.finditer(low))
        if found_days and not found_times:
            # Refresh current days context
            current_days = []
            for tok in found_days:
                key = _strip_accents(tok.lower())
                wd = DAY_NAMES.get(key)
                if wd is not None and wd not in current_days:
                    current_days.append(wd)
            continue
        if found_times:
            # Use current_days if available; otherwise try to detect days within the same line
            days_to_use = list(current_days)
            if not days_to_use and found_days:
                for tok in found_days:
                    key = _strip_accents(tok.lower())
                    wd = DAY_NAMES.get(key)
                    if wd is not None and wd not in days_to_use:
                        days_to_use.append(wd)
            # For each time range on the line, emit slots
            for tm in found_times:
                start = _parse_time_24(tm.group('start'))
                end = _parse_time_24(tm.group('end'))
                if days_to_use:
                    for wd in days_to_use:
                        slots.append((wd, start, end))
            # Reset current days after pairing with a time line
            if days_to_use:
                current_days = []
    # Deduplicate slots
    slots = list({(wd, start, end) for (wd, start, end) in slots})
    # Sort by weekday then start time
    slots.sort(key=lambda x: (x[0], x[1]))
    return slots

def next_weekday(dt, weekday):
    """Return next date for given weekday (0=Monday)."""
    days_ahead = (weekday - dt.weekday() + 7) % 7
    return dt + timedelta(days=days_ahead)

from datetime import timedelta

@app.post("/generate_schedule_ics")
async def generate_schedule_ics(files: List[UploadFile] = File(...)):
    """Detects school schedule in PDF and generates .ics file for Google Calendar."""
    print("[LOG] Starting schedule ICS generation...")
    all_slots = []
    for file in files:
        contenido = await file.read()
        reader = PdfReader(io.BytesIO(contenido))
        texto = "\n".join(page.extract_text() or '' for page in reader.pages)
        slots = extract_schedule(texto)
        if slots:
            print(f"[LOG] Found {len(slots)} schedule slots in {file.filename}")
        all_slots.extend(slots)
    if not all_slots:
        return Response(content=b"No schedule found in uploaded files.", media_type="text/plain")
    # Generate ICS
    cal = Calendar()
    today = datetime.today()
    for idx, (weekday, start, end) in enumerate(all_slots):
        # Find next occurrence of this weekday
        start_time = datetime.strptime(start, "%H:%M")
        end_time = datetime.strptime(end, "%H:%M")
        first_date = next_weekday(today, weekday)
        # Create 15 weekly occurrences
        for wk in range(15):
            occ_start = first_date + timedelta(days=7 * wk)
            event_start = occ_start.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
            event_end = occ_start.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
            event = Event()
            event.name = f"Class Session"
            event.begin = event_start
            event.end = event_end
            event.uid = str(uuid.uuid4())
            event.description = f"Imported from syllabus PDF."
            cal.events.add(event)
    ics_bytes = str(cal).encode("utf-8")
    return Response(content=ics_bytes, media_type="text/calendar", headers={
        "Content-Disposition": "attachment; filename=class_schedule.ics"
    })
from fastapi import FastAPI, UploadFile, File, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import re
import io
from datetime import datetime, timedelta
import traceback

MONTHS = {
    # Spanish
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12,
    # English
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10,
    'november': 11, 'december': 12
}

DATE_PATTERNS = [
    # 12/05 or 12-05
    r"(?P<d1>\d{1,2})[\/\-](?P<m1>\d{1,2})(?:[\/\-](?P<y1>\d{2,4}))?",
    # 12 de mayo (optional year) / 12 mayo / 12 May
    r"(?P<d2>\d{1,2})\s*(?:de\s*)?(?P<m2>\w+)(?:\s+de\s+(?P<y2>\d{4}))?",
    # mayo 12 (optional year) / May 12
    r"(?P<m3>\w+)\s+(?P<d3>\d{1,2})(?:\s+de\s+(?P<y3>\d{4}))?"
]

EVENT_KEYWORDS = [
    # Spanish
    'examen', 'entrega', 'vence', 'tarea', 'proyecto',
    # English
    'exam', 'deadline', 'due', 'assignment', 'project'
]

def try_parse_date(fragment: str) -> datetime | None:
    """Try to normalize a date fragment to datetime (default hour 09:00). Supports Spanish and English."""
    lower = fragment.lower()
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, lower)
        if not m:
            continue
        day = None
        month = None
        year = None
        if m.groupdict().get('d1'):
            day = int(m.group('d1'))
            month = int(m.group('m1'))
            y = m.group('y1')
            if y:
                year = int(y if len(y) == 4 else ('20' + y))
        elif m.groupdict().get('d2'):
            day = int(m.group('d2'))
            month_name = m.group('m2')
            month = MONTHS.get(month_name.lower())
            y = m.group('y2')
            if y:
                year = int(y)
        elif m.groupdict().get('d3'):
            day = int(m.group('d3'))
            month_name = m.group('m3')
            month = MONTHS.get(month_name.lower())
            y = m.group('y3')
            if y:
                year = int(y)
        if day and month:
            if not year:
                today = datetime.today()
                tentative = datetime(today.year, month, day)
                if (tentative - today).days < -30:
                    tentative = datetime(today.year + 1, month, day)
                return tentative.replace(hour=9, minute=0)
            return datetime(year, month, day, 9, 0)
    return None

# NOTE: Removed duplicate FastAPI() instantiation to preserve previously registered routes (e.g., /generate_schedule_ics)

# Permitir CORS para frontend en localhost:5173 y 3000
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "https://syllabus-unifier-web.onrender.com"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],  # incluye OPTIONS
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

# Manejo explícito de preflight para /generar (útil si algún proxy o servidor intermedio no respeta CORS por defecto)
@app.options("/generar")
def preflight_generar():
    return Response(status_code=200)

def extract_dates(text):
    results = []
    for kw in EVENT_KEYWORDS:
        for m_kw in re.finditer(kw, text.lower()):
            start_ctx = max(0, m_kw.start() - 120)
            end_ctx = min(len(text), m_kw.end() + 120)
            contexto = text[start_ctx:end_ctx]
            fecha_encontrada = None
            for pattern in DATE_PATTERNS:
                m_date = re.search(pattern, contexto.lower())
                if m_date:
                    fecha_encontrada = m_date.group(0)
                    break
            if fecha_encontrada:
                results.append(f"{kw.capitalize()}: {fecha_encontrada} | {contexto.strip().replace('\n', ' ')}")
    return results

def extract_section(text, section_names, max_length=1000):
    # Search for section by name (Spanish or English) and extract until next section break
    for name in section_names:
        m = re.search(rf"{name}[:\n]", text, re.IGNORECASE)
        if m:
            start = m.end()
            end = re.search(r"\n[A-ZÁÉÍÓÚÑ ]{4,}[:\n]", text[start:])
            end_idx = start + end.start() if end else start + max_length
            return text[start:end_idx].strip()
    return "Not found"

def extract_contact(text):
    # Search for email and name near keywords (Spanish and English)
    email = re.search(r"[\w\.-]+@[\w\.-]+", text)
    name = None
    for kw in ["profesor", "docente", "contacto", "responsable", "teacher", "instructor", "contact", "faculty"]:
        m = re.search(rf"{kw}[:\n ]+([A-ZÁÉÍÓÚÑa-záéíóúñ ]{{5,}})", text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            break
    return name or "Not found", email.group(0) if email else "Not found"

EVAL_LABEL_HINTS = [
    # Spanish
    "examen", "exámenes", "parcial", "parciales", "final", "tarea", "tareas", "trabajo", "trabajos",
    "proyecto", "proyectos", "práctica", "prácticas", "practica", "practicas", "laboratorio", "laboratorios",
    "participación", "participacion", "asistencia", "quiz", "quices", "exposición", "exposicion", "presentación", "presentacion",
    # English
    "exam", "midterm", "final", "homework", "assignment", "assignments", "project", "projects", "lab",
    "labs", "participation", "attendance", "quiz", "quizzes", "presentation"
]

def extract_evaluation_items(text: str) -> list[str]:
    """Extract evaluation criteria lines like 'Exam - 20%' or '20% Homework'.
    Prefer scanning inside an evaluation/grading section; fallback to keyword lines.
    Returns list of 'Label: XX%'.
    """
    # 1) Try to narrow to an evaluation section
    eval_section = extract_section(
        text,
        [
            "criterios de evaluación", "criterios de evaluacion", "evaluación", "evaluacion",
            "evaluación y calificación", "calificación", "calificacion",
            "evaluation", "grading", "assessment",
        ],
        max_length=1600,
    )
    search_text = eval_section if eval_section and eval_section != "Not found" else text

    items: list[tuple[str, int]] = []
    # Pattern A: Label before percent (e.g., "Examen Final - 30%")
    pat_a = re.compile(r"(?P<label>[A-Za-zÁÉÍÓÚáéíóúñÑ\/( )]{3,}?)\s*[:\-–—]?\s*(?P<pct>\d{1,3})\s*%", re.IGNORECASE)
    # Pattern B: Percent before label (e.g., "30% Proyecto Integrador")
    pat_b = re.compile(r"(?P<pct>\d{1,3})\s*%\s*(?P<label>[A-Za-zÁÉÍÓÚáéíóúñÑ\/( )]{3,})", re.IGNORECASE)

    # Split by lines to reduce cross-line noise
    for raw_line in search_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        low = _strip_accents(line.lower())
        # If not in narrowed section, require at least one hint to avoid false positives
        if search_text is text:
            if not any(h in low for h in EVAL_LABEL_HINTS):
                continue
        m = pat_a.search(line) or pat_b.search(line)
        if not m:
            continue
        label = m.group('label').strip()
        pct = int(m.group('pct'))
        if pct < 0 or pct > 100:
            continue
        # Clean label: collapse spaces and common trailing punctuation
        label = re.sub(r"\s+", " ", label)
        label = re.sub(r"\s*[:\-–—]$", "", label)
        # Heuristic: drop lone words like 'total', 'nota', 'score'
        if _strip_accents(label.lower()) in {"total", "nota", "score"}:
            continue
        items.append((label, pct))

    # Deduplicate by label+percent, keep order
    seen = set()
    out: list[str] = []
    for label, pct in items:
        key = (label.lower(), pct)
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{label}: {pct}%")
    return out

def extract_enumerated_syllabus(text: str, max_items: int = 100) -> list[str]:
    """Extract enumerated syllabus topics like:
    1.1 Tema, 1.2 Tema, 2.3.4 Subtema, and also 1. Tema.
    Returns a flat list preserving order.
    """
    items: list[str] = []
    lines = text.splitlines()
    # 1.1 or 1.1.1 patterns
    pat_multi = re.compile(r"^\s*(?P<num>\d+(?:\.\d+){1,3})\s*[\)\.-]?\s+(?P<title>\S(?:.*\S)?)\s*$")
    # 1. patterns (single level with a dot, parenthesis, or dash)
    pat_single = re.compile(r"^\s*(?P<num>\d+)\s*[\)\.-]\s+(?P<title>\S(?:.*\S)?)\s*$")
    for line in lines:
        m = pat_multi.match(line) or pat_single.match(line)
        if not m:
            continue
        num = m.group('num')
        title = m.group('title').strip()
        # Avoid capturing page numbers or isolated numbers as titles
        if not title or len(title) < 2:
            continue
        # Remove trailing dots from title
        title = re.sub(r"\s*\.+$", "", title)
        items.append(f"{num} {title}")
        if len(items) >= max_items:
            break
    return items

# ------------------------------
# PDF sanitation helpers
# ------------------------------
def sanitize_pdf_header(raw: bytes) -> bytes:
    """Trim leading garbage before %PDF if present."""
    idx = raw.find(b'%PDF')
    if idx > 0:
        return raw[idx:]
    return raw

def pdf_truncated(raw: bytes) -> bool:
    """Detect missing EOF marker (heuristic)."""
    tail = raw[-64:]
    return b'%%EOF' not in tail

def extract_pdf_text(bytes_in: bytes, errores: list[str], fname: str) -> tuple[str, list[str]]:
    """Return extracted text and a list of warnings for this file."""
    warnings: list[str] = []
    sanitized = sanitize_pdf_header(bytes_in)
    if sanitized is not bytes_in:
        warnings.append("Header adjusted (garbage before %PDF removed)")
    if pdf_truncated(bytes_in):
        warnings.append("EOF marker missing or truncated")
    try:
        reader = PdfReader(io.BytesIO(sanitized))
        texto = "\n".join(page.extract_text() or '' for page in reader.pages)
        if not texto.strip():
            warnings.append("No extractable text (possible image-based PDF)")
        return texto, warnings
    except Exception as e:
        errores.append(f"{fname}: PDF parse failed: {e}")
        return "", warnings + ["Parse failed"]

def extract_evaluation_items_from_pdf(pdf_bytes: bytes) -> list[str]:
    """Try to extract evaluation criteria from table structures using pdfplumber.
    It looks for rows where one cell is a numeric weight (e.g., 40 or 40%),
    and uses other cells in the same row to form the label.
    """
    if pdfplumber is None:
        return []
    results: list[tuple[str, int]] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables() or []
                for tb in tables:
                    # Skip too small tables
                    if not tb or len(tb) < 2:
                        continue
                    # Normalize table cells
                    norm = [[(c or '').strip() for c in row] for row in tb]
                    # Try to detect header row if contains 'ponderación'
                    header_idx = 0
                    for i in range(min(2, len(norm))):
                        header_line = ' '.join(norm[i]).lower()
                        if 'ponderacion' in _strip_accents(header_line) or '%' in header_line:
                            header_idx = i
                            break
                    rows = norm[header_idx+1:] if header_idx < len(norm) else norm
                    for row in rows:
                        if not row:
                            continue
                        # Find a numeric cell to use as percent
                        pct_val = None
                        label_parts: list[str] = []
                        for cell in row:
                            txt = (cell or '').strip()
                            if not txt:
                                continue
                            m_pct = re.fullmatch(r"(\d{1,3})\s*%?", _strip_accents(txt))
                            if m_pct:
                                try:
                                    v = int(m_pct.group(1))
                                    if 0 <= v <= 100:
                                        pct_val = v
                                        continue
                                except Exception:
                                    pass
                            # Non-numeric, part of label
                            label_parts.append(txt)
                        if pct_val is not None and label_parts:
                            label = ' '.join(label_parts)
                            # Collapse whitespace
                            label = re.sub(r"\s+", " ", label)
                            # Trim overly generic tails
                            label = label.strip(' -:\u2013\u2014')
                            results.append((label, pct_val))
    except Exception:
        return []
    # Dedup and stringify
    seen = set()
    out: list[str] = []
    for label, pct in results:
        key = (label.lower(), pct)
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{label}: {pct}%")
    return out

def extract_evaluation_items_numeric_blocks(text: str) -> list[str]:
    """Fallback parser for blocky layouts where weights appear as standalone numbers
    (e.g., a 'PONDERACIÓN' column) and labels are contiguous text around them.
    Heuristic: accumulate consecutive non-numeric lines as label; when a numeric-only
    line (<=100) is encountered, emit label: pct% and reset.
    Prefer running this within the evaluation section if available.
    """
    # Narrow to evaluation section if possible
    section = extract_section(
        text,
        [
            "criterios de evaluación", "criterios de evaluacion", "evaluación", "evaluacion",
            "evaluación y calificación", "calificación", "calificacion",
            "evaluation", "grading", "assessment", "ponderación", "ponderacion",
        ],
        max_length=3000,
    )
    search_text = section if section and section != "Not found" else text

    items: list[tuple[str, int]] = []
    label_buf: list[str] = []
    for raw in search_text.splitlines():
        line = (raw or '').strip()
        if not line:
            continue
        # If it's a pure number or number with %
        m = re.fullmatch(r"(\d{1,3})\s*%?", _strip_accents(line))
        if m:
            try:
                v = int(m.group(1))
                if 0 <= v <= 100 and label_buf:
                    label = ' '.join(label_buf)
                    label = re.sub(r"\s+", " ", label).strip(' -:\u2013\u2014')
                    items.append((label, v))
                    label_buf = []
                    continue
            except Exception:
                pass
        # Otherwise, accumulate text parts (skip headers like PONDERACIÓN single word)
        low = _strip_accents(line.lower())
        if low in {"ponderacion", "ponderación"}:
            continue
        label_buf.append(line)

    # Dedup and stringify
    seen = set()
    out: list[str] = []
    for label, pct in items:
        key = (label.lower(), pct)
        if key in seen:
            continue
        seen.add(key)
        out.append(f"{label}: {pct}%")
    return out

# ------------------------------
# Helpers separados para syllabus y schedule
# ------------------------------
async def build_syllabus_pdf(files: List[UploadFile]) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Unified Academic Summary")
    y -= 30
    c.setFont("Helvetica", 12)
    errores: list[str] = []
    try:
        for idx, file in enumerate(files):
            try:
                nombre_curso = file.filename.rsplit('.', 1)[0]
                contenido = await file.read()
                texto, pdf_warnings = extract_pdf_text(contenido, errores, file.filename)
                fechas = extract_dates(texto)
                temas = extract_section(texto, ["temario", "contenidos", "unidades", "temas"])
                enum_temas = extract_enumerated_syllabus(texto)
                recursos = extract_section(texto, ["bibliografía", "recursos", "lecturas", "material"])
                nombre, email = extract_contact(texto)
                reglamento = extract_section(texto, ["reglamento", "normas", "política", "condiciones"])
                c.setFont("Helvetica-Bold", 14)
                c.drawString(40, y, f"Course: {nombre_curso}")
                y -= 22
                # Suppress PDF warnings output per user request; still collected internally if needed.
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Important dates:")
                y -= 18
                c.setFont("Helvetica", 11)
                for f in fechas:
                    c.drawString(60, y, f[:110])
                    y -= 14
                    if y < 80:
                        c.showPage(); y = height - 40
                # Evaluation criteria (prefer table-extracted > regex > numeric blocks)
                eval_items = extract_evaluation_items_from_pdf(contenido)
                if not eval_items:
                    eval_items = extract_evaluation_items(texto)
                if not eval_items:
                    eval_items = extract_evaluation_items_numeric_blocks(texto)
                if eval_items:
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, "Evaluation criteria:")
                    y -= 18
                    c.setFont("Helvetica", 11)
                    for item in eval_items:
                        c.drawString(60, y, item[:110])
                        y -= 14
                        if y < 80:
                            c.showPage(); y = height - 40
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Syllabus:")
                y -= 18
                c.setFont("Helvetica", 11)
                if enum_temas:
                    for line in enum_temas:
                        c.drawString(60, y, line[:110])
                        y -= 14
                        if y < 80:
                            c.showPage(); y = height - 40
                else:
                    for line in temas.splitlines():
                        c.drawString(60, y, line[:110])
                        y -= 14
                        if y < 80:
                            c.showPage(); y = height - 40
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Resources and bibliography:")
                y -= 18
                c.setFont("Helvetica", 11)
                for line in recursos.splitlines():
                    c.drawString(60, y, line[:110])
                    y -= 14
                    if y < 80:
                        c.showPage(); y = height - 40
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Instructor contact:")
                y -= 18
                c.setFont("Helvetica", 11)
                c.drawString(60, y, f"Name: {nombre}")
                y -= 14
                c.drawString(60, y, f"Email: {email}")
                y -= 18
                if y < 80:
                    c.showPage(); y = height - 40
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Special rules:")
                y -= 18
                c.setFont("Helvetica", 11)
                for line in reglamento.splitlines():
                    c.drawString(60, y, line[:110])
                    y -= 14
                    if y < 80:
                        c.showPage(); y = height - 40
                y -= 20
                if y < 80:
                    c.showPage(); y = height - 40
            except Exception as e:
                errores.append(f"{file.filename}: {e}")
        if errores:
            c.showPage()
            c.setFont("Helvetica-Bold", 14)
            c.drawString(40, height - 60, "Files with processing errors:")
            c.setFont("Helvetica", 11)
            yerr = height - 90
            for msg in errores:
                c.drawString(60, yerr, msg[:110])
                yerr -= 14
                if yerr < 80:
                    c.showPage(); yerr = height - 60
    finally:
        c.save()
        buffer.seek(0)
    return buffer.read()

def _parse_semester_start(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except Exception:
        return None

async def build_schedule_ics(files: List[UploadFile], semester_start: str | None = None) -> bytes | None:
    # Este endpoint asume que los archivos enviados corresponden a horarios.
    # Procesamos todos los PDF recibidos para mayor tolerancia.
    all_slots = []
    for file in files:
        contenido = await file.read()
        # Sanitize before positional/table extraction attempts
        contenido = sanitize_pdf_header(contenido)
        # 1) Intento posicional con pdfplumber si está disponible
        used_positional = False
        if pdfplumber is not None:
            try:
                with pdfplumber.open(io.BytesIO(contenido)) as pdf:
                    for page in pdf.pages:
                        words = page.extract_words(use_text_flow=True, keep_blank_chars=False) or []
                        # Mapear columnas de días por su x-center
                        headers = {}
                        for w in words:
                            txt = _strip_accents((w.get('text') or '').strip().lower())
                            if txt in DAY_NAMES:
                                x_center = (w.get('x0', 0) + w.get('x1', 0)) / 2
                                weekday = DAY_NAMES[txt]
                                headers[weekday] = headers.get(weekday, []) + [x_center]
                        day_columns = {wd: sum(xs)/len(xs) for wd, xs in headers.items() if xs}
                        if day_columns:
                            # Buscar rangos de tiempo y asociarlos solo a columnas con contenido en esa fila
                            # 1) Construir índices de palabras por proximidad vertical
                            buckets: dict[int, list[dict]] = {}
                            for w in words:
                                top = w.get('top', 0)
                                key = round(top / 2)  # buckets más finos
                                buckets.setdefault(key, []).append(w)
                            # 2) En cada bucket, detectar rangos de tiempo y su banda vertical
                            time_re = re.compile(rf"(?P<start>{TIME_TOKEN})\s*(?:-|–|—|a|to)\s*(?P<end>{TIME_TOKEN})", re.IGNORECASE)
                            for _, wlist in buckets.items():
                                wlist.sort(key=lambda w: w.get('x0', 0))
                                line_text = ' '.join((w.get('text') or '') for w in wlist)
                                for tm in time_re.finditer(line_text):
                                    start = _parse_time_24(tm.group('start'))
                                    end = _parse_time_24(tm.group('end'))
                                    # Calcular centro vertical de la fila usando palabras numéricas
                                    numeric_words = [w for w in wlist if re.search(r"\d", (w.get('text') or ''))]
                                    if not numeric_words:
                                        continue
                                    y_center = sum((w.get('top', 0) + w.get('bottom', 0)) / 2 for w in numeric_words) / len(numeric_words)
                                    # Asociar solo a columnas con texto no-horario cerca de esa banda
                                    for weekday, col_x in day_columns.items():
                                        # Palabras cerca de la columna y banda vertical
                                        candidates = []
                                        for w in wlist:
                                            wx = (w.get('x0', 0) + w.get('x1', 0)) / 2
                                            wy = (w.get('top', 0) + w.get('bottom', 0)) / 2
                                            txt = (w.get('text') or '').strip()
                                            if not txt:
                                                continue
                                            # ignorar encabezados de días y tokens horarios
                                            low = _strip_accents(txt.lower())
                                            if low in DAY_NAMES:
                                                continue
                                            if re.fullmatch(TIME_TOKEN, low):
                                                continue
                                            if abs(wx - col_x) <= 60 and abs(wy - y_center) <= 8:
                                                candidates.append(txt)
                                        if candidates:
                                            all_slots.append((weekday, start, end))
                used_positional = True
            except Exception:
                used_positional = False
        # 2) Fallback por texto si no se pudo usar posicional o si no produjo slots
        if not used_positional or not all_slots:
            try:
                reader = PdfReader(io.BytesIO(contenido))
                texto = "\n".join(page.extract_text() or '' for page in reader.pages)
            except Exception:
                texto = ""
            if texto:
                slots = extract_schedule(texto)
                all_slots.extend(slots)
    if not all_slots:
        return None
    cal = Calendar()
    # Anchor to semester_start if provided; else use next weekday from today
    anchor_date = _parse_semester_start(semester_start)
    today = datetime.today()
    for (weekday, start, end) in all_slots:
        # Skip weekends by default to avoid false positives (enable if you truly have weekend classes)
        if weekday >= 5:
            continue
        start_time = datetime.strptime(start, "%H:%M")
        end_time = datetime.strptime(end, "%H:%M")
        if anchor_date is not None:
            # find the date in the anchor week that matches this weekday
            # compute Monday of anchor week
            anchor_monday = anchor_date - timedelta(days=anchor_date.weekday())
            first_date = anchor_monday + timedelta(days=weekday)
            # if anchor_date is after that weekday within the same week, push to next week to keep future
            if first_date < anchor_date:
                first_date = first_date + timedelta(days=7)
            first_date = datetime.combine(first_date, datetime.min.time())
        else:
            first_date = next_weekday(today, weekday)
        # Crear 15 ocurrencias semanales
        for wk in range(15):
            occ_start = first_date + timedelta(days=7 * wk)
            event_start = occ_start.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
            event_end = occ_start.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
            event = Event()
            event.name = "Class Session"
            # Keep naive datetimes (no 'Z' UTC) to avoid timezone shifts on import
            event.begin = event_start
            event.end = event_end
            event.uid = str(uuid.uuid4())
            event.description = "Imported from schedule PDF."
            cal.events.add(event)
    return str(cal).encode("utf-8")

# ------------------------------
# Endpoints separados
# ------------------------------
@app.post("/syllabus")
async def endpoint_syllabus(files: List[UploadFile] = File(...)):
    pdf_bytes = await build_syllabus_pdf(files)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": "attachment; filename=syllabus_unificado.pdf"
    })

@app.post("/schedule")
async def endpoint_schedule(files: List[UploadFile] = File(...), semester_start: str | None = Form(None)):
    ics_bytes = await build_schedule_ics(files, semester_start=semester_start)
    if not ics_bytes:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={"detail": "No schedule found in uploaded files."})
    return Response(content=ics_bytes, media_type="text/calendar", headers={
        "Content-Disposition": "attachment; filename=class_schedule.ics"
    })

@app.post("/generar")
async def generar_pdf(files: List[UploadFile] = File(...), semester_start: str | None = Form(None)):
    print("[LOG] Iniciando procesamiento de archivos...")
    from fastapi.responses import StreamingResponse
    import tempfile
    import os
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Unified Academic Summary")
    y -= 30
    c.setFont("Helvetica", 12)
    errores: list[str] = []
    schedule_files = []
    syllabus_files = []
    # Clasificar archivos
    for file in files:
        fname = file.filename.lower()
        if "horario" in fname or "schedule" in fname:
            schedule_files.append(file)
        else:
            syllabus_files.append(file)
    # Generar ICS con la misma lógica robusta que el endpoint /schedule
    ics_bytes = None
    if schedule_files:
        try:
            ics_bytes = await build_schedule_ics(schedule_files, semester_start=semester_start)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ERROR] Falló la generación de ICS (combinado): {e}\n{tb}")
            errores.append(f"ICS: {e}")
    # Procesar archivos de syllabus para el PDF resumen
    pdf_bytes = None
    if syllabus_files:
        try:
            for idx, file in enumerate(syllabus_files):
                try:
                    print(f"[LOG] Procesando archivo {idx+1}/{len(syllabus_files)}: {file.filename}")
                    nombre_curso = file.filename.rsplit('.', 1)[0]
                    contenido = await file.read()
                    print(f"[LOG] Leyendo PDF: {file.filename}")
                    texto, pdf_warnings = extract_pdf_text(contenido, errores, file.filename)
                    print(f"[LOG] Extrayendo fechas importantes...")
                    fechas = extract_dates(texto)
                    print(f"[LOG] Extrayendo temario...")
                    temas = extract_section(texto, ["temario", "contenidos", "unidades", "temas"])
                    enum_temas = extract_enumerated_syllabus(texto)
                    print(f"[LOG] Extrayendo recursos y bibliografía...")
                    recursos = extract_section(texto, ["bibliografía", "recursos", "lecturas", "material"])
                    print(f"[LOG] Extrayendo contacto docente...")
                    nombre, email = extract_contact(texto)
                    print(f"[LOG] Extrayendo reglamento especial...")
                    reglamento = extract_section(texto, ["reglamento", "normas", "política", "condiciones"])
                    print(f"[LOG] Generando PDF para {nombre_curso}")
                    c.setFont("Helvetica-Bold", 14)
                    c.drawString(40, y, f"Course: {nombre_curso}")
                    y -= 22
                    # Suppress PDF warnings output per user request.
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, "Important dates:")
                    y -= 18
                    c.setFont("Helvetica", 11)
                    for f in fechas:
                        c.drawString(60, y, f[:110])
                        y -= 14
                        if y < 80:
                            c.showPage(); y = height - 40
                    # Evaluation criteria (prefer table-extracted > regex > numeric blocks)
                    eval_items = extract_evaluation_items_from_pdf(contenido)
                    if not eval_items:
                        eval_items = extract_evaluation_items(texto)
                    if not eval_items:
                        eval_items = extract_evaluation_items_numeric_blocks(texto)
                    if eval_items:
                        c.setFont("Helvetica-Bold", 12)
                        c.drawString(40, y, "Evaluation criteria:")
                        y -= 18
                        c.setFont("Helvetica", 11)
                        for item in eval_items:
                            c.drawString(60, y, item[:110])
                            y -= 14
                            if y < 80:
                                c.showPage(); y = height - 40
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, "Syllabus:")
                    y -= 18
                    c.setFont("Helvetica", 11)
                    if enum_temas:
                        for line in enum_temas:
                            c.drawString(60, y, line[:110])
                            y -= 14
                            if y < 80:
                                c.showPage(); y = height - 40
                    else:
                        for line in temas.splitlines():
                            c.drawString(60, y, line[:110])
                            y -= 14
                            if y < 80:
                                c.showPage(); y = height - 40
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, "Resources and bibliography:")
                    y -= 18
                    c.setFont("Helvetica", 11)
                    for line in recursos.splitlines():
                        c.drawString(60, y, line[:110])
                        y -= 14
                        if y < 80:
                            c.showPage(); y = height - 40
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, "Instructor contact:")
                    y -= 18
                    c.setFont("Helvetica", 11)
                    c.drawString(60, y, f"Name: {nombre}")
                    y -= 14
                    c.drawString(60, y, f"Email: {email}")
                    y -= 18
                    if y < 80:
                        c.showPage(); y = height - 40
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, "Special rules:")
                    y -= 18
                    c.setFont("Helvetica", 11)
                    for line in reglamento.splitlines():
                        c.drawString(60, y, line[:110])
                        y -= 14
                        if y < 80:
                            c.showPage(); y = height - 40
                    y -= 20
                    if y < 80:
                        c.showPage(); y = height - 40
                    print(f"[LOG] PDF generado para {nombre_curso}")
                except Exception as e:
                    tb = traceback.format_exc()
                    print(f"[ERROR] Falló el procesamiento de {file.filename}: {e}\n{tb}")
                    errores.append(f"{file.filename}: {e}")
            if errores:
                c.showPage()
                c.setFont("Helvetica-Bold", 14)
                c.drawString(40, height - 60, "Files with processing errors:")
                c.setFont("Helvetica", 11)
                yerr = height - 90
                for msg in errores:
                    c.drawString(60, yerr, msg[:110])
                    yerr -= 14
                    if yerr < 80:
                        c.showPage(); yerr = height - 60
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ERROR] Unexpected failure en PDF resumen: {e}\n{tb}")
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, y, "An unexpected error occurred during processing.")
        finally:
            c.save()
            buffer.seek(0)
            print("[LOG] Final PDF generated and ready to send to frontend.")
            pdf_bytes = buffer.read()
    # ics_bytes ya contiene el calendario si había archivos de horario
    # Responder un único archivo simple para facilitar al frontend
    from fastapi.responses import Response
    if pdf_bytes and ics_bytes:
        # Crear ZIP con ambos
        import zipfile
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('syllabus_unificado.pdf', pdf_bytes)
            zf.writestr('class_schedule.ics', ics_bytes)
        zip_buffer.seek(0)
        return Response(content=zip_buffer.read(), media_type="application/zip", headers={
            "Content-Disposition": "attachment; filename=syllabus_and_schedule.zip"
        })
    if pdf_bytes and not ics_bytes:
        return Response(content=pdf_bytes, media_type="application/pdf", headers={
            "Content-Disposition": "attachment; filename=syllabus_unificado.pdf"
        })
    if ics_bytes and not pdf_bytes:
        return Response(content=ics_bytes, media_type="text/calendar", headers={
            "Content-Disposition": "attachment; filename=class_schedule.ics"
        })
    return Response(content=b"No syllabus or schedule found.", media_type="text/plain")
