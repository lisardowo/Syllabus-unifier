from fastapi import FastAPI, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from ics import Calendar, Event
from pypdf import PdfReader
import re
import io
from datetime import datetime

MONTHS_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12
}

DATE_PATTERNS = [
    # 12/05 or 12-05
    r"(?P<d1>\d{1,2})[\/\-](?P<m1>\d{1,2})(?:[\/\-](?P<y1>\d{2,4}))?",
    # 12 de mayo (optional year) / 12 mayo
    r"(?P<d2>\d{1,2})\s*(?:de\s*)?(?P<m2>\w+)(?:\s+de\s+(?P<y2>\d{4}))?",
    # mayo 12 (optional year)
    r"(?P<m3>\w+)\s+(?P<d3>\d{1,2})(?:\s+de\s+(?P<y3>\d{4}))?"
]

EVENT_KEYWORDS = ['examen', 'entrega', 'vence', 'tarea', 'proyecto']

def try_parse_date(fragment: str) -> datetime | None:
    """Intentar normalizar un fragmento de fecha a datetime (sin hora -> 09:00)."""
    lower = fragment.lower()
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, lower)
        if not m:
            continue
        # Extract possible groups
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
            month = MONTHS_ES.get(month_name.lower())
            y = m.group('y2')
            if y:
                year = int(y)
        elif m.groupdict().get('d3'):
            day = int(m.group('d3'))
            month_name = m.group('m3')
            month = MONTHS_ES.get(month_name.lower())
            y = m.group('y3')
            if y:
                year = int(y)
        if day and month:
            if not year:
                # Heurística: usar año actual, y si la fecha ya pasó más de 30 días, asumir próximo año (cursos cruzando año nuevo)
                today = datetime.today()
                tentative = datetime(today.year, month, day)
                if (tentative - today).days < -30:
                    tentative = datetime(today.year + 1, month, day)
                return tentative.replace(hour=9, minute=0)  # hora por defecto
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
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/generar")
async def generar_calendario(files: List[UploadFile] = File(...)):
    """Genera un calendario .ics unificando eventos detectados en múltiples PDFs."""
    calendario = Calendar()
    # Texto ampliado por archivo para búsquedas; se procesa curso a curso
    for file in files:
        nombre_curso = file.filename.rsplit('.', 1)[0]
        contenido = await file.read()
        reader = PdfReader(io.BytesIO(contenido))
        texto_syllabus = "\n".join(page.extract_text() or '' for page in reader.pages)
        # Para cada keyword buscamos ventanas de contexto que tengan una fecha cercana
        lowered = texto_syllabus.lower()
        for kw in EVENT_KEYWORDS:
            for m_kw in re.finditer(kw, lowered):
                # Expandir ventana alrededor del keyword
                start_ctx = max(0, m_kw.start() - 120)
                end_ctx = min(len(texto_syllabus), m_kw.end() + 120)
                contexto = texto_syllabus[start_ctx:end_ctx]
                # Intentar localizar la primera fecha parseable dentro del contexto
                fecha_encontrada = None
                for pattern in DATE_PATTERNS:
                    m_date = re.search(pattern, contexto.lower())
                    if m_date:
                        fecha_encontrada = m_date.group(0)
                        break
                dt = try_parse_date(fecha_encontrada) if fecha_encontrada else None
                if dt:
                    evento = Event()
                    evento.name = f"[{nombre_curso}] {kw.capitalize()} - {contexto.strip().replace('\n', ' ')}"
                    evento.begin = dt
                    calendario.events.add(evento)
    ics_str = str(calendario)
    return Response(content=ics_str, media_type="text/calendar", headers={
        "Content-Disposition": "attachment; filename=calendario_unificado.ics"
    })
