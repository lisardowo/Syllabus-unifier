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

# Day token and time patterns (supports AM/PM and minute-optional)
DAY_TOKEN = r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun|lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo|lun|mar|mie|mié|jue|vie|sab|sáb|dom|lu|ma|mi|ju|vi|sa|do"
TIME_TOKEN = r"\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?"
SCHEDULE_PATTERN = re.compile(
    rf"(?P<days>(?:{DAY_TOKEN})(?:\s*(?:/|,|y|and|&)+\s*(?:{DAY_TOKEN}))*)\s*[:\-–—]?\s*(?P<start>{TIME_TOKEN})\s*(?:-|–|—|a|to)\s*(?P<end>{TIME_TOKEN})",
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
        for day_token in re.findall(rf"{DAY_TOKEN}", days_raw, flags=re.IGNORECASE):
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
        event_start = first_date.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
        event_end = first_date.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
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
from fastapi import FastAPI, UploadFile, File, Response
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

app = FastAPI()

# Permitir CORS para frontend en localhost:5173 y 3000
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
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
                reader = PdfReader(io.BytesIO(contenido))
                texto = "\n".join(page.extract_text() or '' for page in reader.pages)
                fechas = extract_dates(texto)
                temas = extract_section(texto, ["temario", "contenidos", "unidades", "temas"])
                recursos = extract_section(texto, ["bibliografía", "recursos", "lecturas", "material"])
                nombre, email = extract_contact(texto)
                reglamento = extract_section(texto, ["reglamento", "normas", "política", "condiciones"])
                c.setFont("Helvetica-Bold", 14)
                c.drawString(40, y, f"Course: {nombre_curso}")
                y -= 22
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Important dates:")
                y -= 18
                c.setFont("Helvetica", 11)
                for f in fechas:
                    c.drawString(60, y, f[:110])
                    y -= 14
                    if y < 80:
                        c.showPage(); y = height - 40
                c.setFont("Helvetica-Bold", 12)
                c.drawString(40, y, "Syllabus:")
                y -= 18
                c.setFont("Helvetica", 11)
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

async def build_schedule_ics(files: List[UploadFile]) -> bytes | None:
    # Este endpoint asume que los archivos enviados corresponden a horarios.
    # Procesamos todos los PDF recibidos para mayor tolerancia.
    all_slots = []
    for file in files:
        contenido = await file.read()
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
                            # Agrupar palabras por línea (tolerancia vertical)
                            lines = {}
                            for w in words:
                                top = w.get('top', 0)
                                key = round(top / 3)  # bucket simple
                                lines.setdefault(key, []).append(w)
                            for _, wlist in lines.items():
                                wlist.sort(key=lambda w: w.get('x0', 0))
                                line_text = ' '.join(w.get('text', '') for w in wlist)
                                # Buscar rangos de tiempo en la línea
                                for tm in re.finditer(rf"(?P<start>{TIME_TOKEN})\s*(?:-|–|—|a|to)\s*(?P<end>{TIME_TOKEN})", line_text, flags=re.IGNORECASE):
                                    start = _parse_time_24(tm.group('start'))
                                    end = _parse_time_24(tm.group('end'))
                                    # Estimar x-center de los tokens numéricos en la línea
                                    numeric_words = [w for w in wlist if re.search(r"\d", w.get('text',''))]
                                    if not numeric_words:
                                        continue
                                    x_center = sum((w.get('x0',0)+w.get('x1',0))/2 for w in numeric_words)/len(numeric_words)
                                    # Asignar al día más cercano según columnas
                                    if day_columns:
                                        nearest_day = min(day_columns.items(), key=lambda kv: abs(kv[1]-x_center))[0]
                                        all_slots.append((nearest_day, start, end))
                            used_positional = True
            except Exception:
                used_positional = False
        # 2) Fallback por texto si no se pudo usar posicional o si no produjo slots
        if not used_positional or not all_slots:
            reader = PdfReader(io.BytesIO(contenido))
            texto = "\n".join(page.extract_text() or '' for page in reader.pages)
            slots = extract_schedule(texto)
            all_slots.extend(slots)
    if not all_slots:
        return None
    cal = Calendar()
    today = datetime.today()
    for (weekday, start, end) in all_slots:
        start_time = datetime.strptime(start, "%H:%M")
        end_time = datetime.strptime(end, "%H:%M")
        first_date = next_weekday(today, weekday)
        event_start = first_date.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
        event_end = first_date.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
        event = Event()
        event.name = "Class Session"
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
async def endpoint_schedule(files: List[UploadFile] = File(...)):
    ics_bytes = await build_schedule_ics(files)
    if not ics_bytes:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=422, content={"detail": "No schedule found in uploaded files."})
    return Response(content=ics_bytes, media_type="text/calendar", headers={
        "Content-Disposition": "attachment; filename=class_schedule.ics"
    })

@app.post("/generar")
async def generar_pdf(files: List[UploadFile] = File(...)):
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
    all_slots = []
    # Procesar archivos de horario para eventos académicos
    for file in schedule_files:
        try:
            contenido = await file.read()
            reader = PdfReader(io.BytesIO(contenido))
            texto = "\n".join(page.extract_text() or '' for page in reader.pages)
            slots = extract_schedule(texto)
            if slots:
                all_slots.extend(slots)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[ERROR] Falló el procesamiento de horario {file.filename}: {e}\n{tb}")
            errores.append(f"Horario {file.filename}: {e}")
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
                    reader = PdfReader(io.BytesIO(contenido))
                    texto = "\n".join(page.extract_text() or '' for page in reader.pages)
                    print(f"[LOG] Extrayendo fechas importantes...")
                    fechas = extract_dates(texto)
                    print(f"[LOG] Extrayendo temario...")
                    temas = extract_section(texto, ["temario", "contenidos", "unidades", "temas"])
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
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, "Important dates:")
                    y -= 18
                    c.setFont("Helvetica", 11)
                    for f in fechas:
                        c.drawString(60, y, f[:110])
                        y -= 14
                        if y < 80:
                            c.showPage(); y = height - 40
                    c.setFont("Helvetica-Bold", 12)
                    c.drawString(40, y, "Syllabus:")
                    y -= 18
                    c.setFont("Helvetica", 11)
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
    # Si hay horarios, generar ICS
    ics_bytes = None
    if all_slots:
        cal = Calendar()
        today = datetime.today()
        for idx, (weekday, start, end) in enumerate(all_slots):
            start_time = datetime.strptime(start, "%H:%M")
            end_time = datetime.strptime(end, "%H:%M")
            first_date = next_weekday(today, weekday)
            event_start = first_date.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
            event_end = first_date.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
            event = Event()
            event.name = f"Class Session"
            event.begin = event_start
            event.end = event_end
            event.uid = str(uuid.uuid4())
            event.description = f"Imported from schedule PDF."
            cal.events.add(event)
        ics_bytes = str(cal).encode("utf-8")
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
