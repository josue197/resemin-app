
from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from pydantic import BaseModel

# --- Config simulada ---
ADMIN_PASSWORD = "TuClaveSecreta123"

app = FastAPI(title="Mock ReseMin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # para pruebas locales del portal en http://127.0.0.1:5500
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estado en memoria
STATE = {
    "columns": [
        "EMPRESA", "DESCRIPCION_EMPRESA", "CODIGO_UNIDAD", "DESCRIPCION_UNIDAD",
        "ANNO", "PERIODO", "CORRELATIVO", "TRABAJADOR", "NOMBRE_TRABAJADOR",
        "TIPO_DOCUMENTO", "NUMERO_DOCUMENTO", "CODIGO_PLANILLA", "DESCRIPCION_PLANILLA",
        "CODIGO_SEDE", "DESCRIPCION_SEDE", "CODIGO_DEPARTAMENTO", "DESCRIPCION_DEPARTAMENTO",
        "CODIGO_AREA", "DESCRIPCION_AREA", "CODIGO_SECCION", "DESCRIPCION_SECCION",
        "CENTRO_DE_COSTO", "DESCRIPCION_CENTRO_DE_COSTO", "FECHA_NACIMIENTO",
        "FECHA_INGRESO_EMPRESA", "FECHA_CESE", "CODIGO_PUESTO_TRABAJADOR",
        "DESCIPCION_PUESTO_TRABAJADOR"
    ],
    "rows": [
        {
            "EMPRESA": "RESEMIN",
            "TRABAJADOR": "12345678",
            "NOMBRE_TRABAJADOR": "JUAN PEREZ",
            "TIPO_DOCUMENTO": "DNI",
            "NUMERO_DOCUMENTO": "12345678",
            "DESCRIPCION_PLANILLA": "PLANILLA PRINCIPAL",
            "DESCIPCION_PUESTO_TRABAJADOR": "OPERARIO",
            "FECHA_INGRESO_EMPRESA": "2023-01-15",
            "FECHA_CESE": ""
        },
        {
            "EMPRESA": "RESEMIN",
            "TRABAJADOR": "87654321",
            "NOMBRE_TRABAJADOR": "MARIA LOPEZ",
            "TIPO_DOCUMENTO": "DNI",
            "NUMERO_DOCUMENTO": "87654321",
            "DESCRIPCION_PLANILLA": "PLANILLA PRINCIPAL",
            "DESCIPCION_PUESTO_TRABAJADOR": "ANALISTA",
            "FECHA_INGRESO_EMPRESA": "2024-06-01",
            "FECHA_CESE": ""
        }
    ],
    "config": {
        "dni_column": "TRABAJADOR",
        "fecha_column": "FECHA_INGRESO_EMPRESA",
        "visible_columns": [
            "EMPRESA", "NOMBRE_TRABAJADOR", "TIPO_DOCUMENTO", "NUMERO_DOCUMENTO",
            "DESCRIPCION_PLANILLA", "DESCIPCION_PUESTO_TRABAJADOR", "FECHA_INGRESO_EMPRESA"
        ]
    }
}

def require_admin(x_admin_password: Optional[str]):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid X-Admin-Password")

@app.get("/")
def root():
    return {"status": "ok", "service": "mock"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# --- Admin: simular upload ---
@app.post("/admin/upload")
async def admin_upload(file: UploadFile = File(...), x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")):
    require_admin(x_admin_password)
    # No procesamos el Excel, solo devolvemos columnas y conteo simulado
    return {"columns": STATE["columns"], "rows_count": len(STATE["rows"])}

# --- Admin: guardar config (acepta JSON o Form, pero aquí lo simplificamos) ---
class ConfigPayload(BaseModel):
    dni_column: str
    fecha_column: str
    visible_columns: List[str]

@app.post("/admin/config")
async def admin_config(
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
    payload: ConfigPayload = Body(...)
):
    require_admin(x_admin_password)
    # Validación simple contra columnas existentes
    cols = STATE["columns"]
    missing = [c for c in [payload.dni_column, payload.fecha_column] + payload.visible_columns if c not in cols]
    if missing:
        raise HTTPException(status_code=400, detail={"error": "Columnas no encontradas", "faltantes": missing})
    STATE["config"] = payload.dict()
    return {"status": "ok", "config": STATE["config"]}

@app.get("/admin/status")
def admin_status(x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password")):
    require_admin(x_admin_password)
    return {"employees": len(STATE["rows"]), "config": STATE["config"]}

# --- Públicos ---
@app.get("/public/columns")
def public_columns():
    return {"visible_columns": STATE["config"]["visible_columns"]}

@app.get("/public/query")
def public_query(dni: str, fecha: str):
    dni_col = STATE["config"]["dni_column"]
    fecha_col = STATE["config"]["fecha_column"]
    visible = STATE["config"]["visible_columns"]

    # Filtro básico simulando la consulta
    matches = [
        {k: row.get(k) for k in visible}
        for row in STATE["rows"]
        if str(row.get(dni_col)) == str(dni) and str(row.get(fecha_col)) == str(fecha)
    ]
