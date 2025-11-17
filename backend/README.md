## Ejecutar el backend

Opción A (desde esta carpeta `backend/`):

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Opción B (desde la raíz del repo):

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Verificar salud:

```
curl http://localhost:8000/health
```

Debe responder:

```
{"status":"ok"}
```
