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

## Configuración de CORS / Render

El backend permite CORS hacia orígenes conocidos y también usa una variable de entorno opcional para agregar tu frontend desplegado:

- Variable: `FRONTEND_URL`
	- Ejemplo (Render): `https://syllabus-unifier-web.onrender.com`

Además, ya está incluido explícitamente `https://syllabus-unifier-web.onrender.com` en la lista por defecto. Si usas otro dominio, define `FRONTEND_URL` para añadirlo.

```
