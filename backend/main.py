from fastapi import FastAPI, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
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
    # Busca la sección por nombre y extrae hasta el siguiente salto de sección
    for name in section_names:
        m = re.search(rf"{name}[:\n]", text, re.IGNORECASE)
        if m:
            start = m.end()
            # Busca el siguiente título de sección (mayúsculas, salto de línea, etc)
            end = re.search(r"\n[A-ZÁÉÍÓÚÑ ]{4,}[:\n]", text[start:])
            end_idx = start + end.start() if end else start + max_length
            return text[start:end_idx].strip()
    return "No encontrado"

def extract_contact(text):
    # Busca email y nombre cerca de palabras clave
    email = re.search(r"[\w\.-]+@[\w\.-]+", text)
    name = None
    for kw in ["profesor", "docente", "contacto", "responsable"]:
        m = re.search(rf"{kw}[:\n ]+([A-ZÁÉÍÓÚÑa-záéíóúñ ]{{5,}})", text, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            break
    return name or "No encontrado", email.group(0) if email else "No encontrado"

@app.post("/generar")
async def generar_pdf(files: List[UploadFile] = File(...)):
    print("[LOG] Iniciando procesamiento de archivos...")
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 40
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Resumen Académico Unificado")
    y -= 30
    c.setFont("Helvetica", 12)
    for idx, file in enumerate(files):
        print(f"[LOG] Procesando archivo {idx+1}/{len(files)}: {file.filename}")
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
        c.drawString(40, y, f"Curso: {nombre_curso}")
        y -= 22
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Fechas importantes:")
        y -= 18
        c.setFont("Helvetica", 11)
        for f in fechas:
            c.drawString(60, y, f[:110])
            y -= 14
            if y < 80:
                c.showPage(); y = height - 40
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Temario:")
        y -= 18
        c.setFont("Helvetica", 11)
        for line in temas.splitlines():
            c.drawString(60, y, line[:110])
            y -= 14
            if y < 80:
                c.showPage(); y = height - 40
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Recursos y bibliografía:")
        y -= 18
        c.setFont("Helvetica", 11)
        for line in recursos.splitlines():
            c.drawString(60, y, line[:110])
            y -= 14
            if y < 80:
                c.showPage(); y = height - 40
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Contacto docente:")
        y -= 18
        c.setFont("Helvetica", 11)
        c.drawString(60, y, f"Nombre: {nombre}")
        y -= 14
        c.drawString(60, y, f"Email: {email}")
        y -= 18
        if y < 80:
            c.showPage(); y = height - 40
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, "Reglamento especial:")
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
    c.save()
    buffer.seek(0)
    print("[LOG] PDF final generado y listo para enviar al frontend.")
    return Response(content=buffer.read(), media_type="application/pdf", headers={
        "Content-Disposition": "attachment; filename=syllabus_unificado.pdf"
    })
