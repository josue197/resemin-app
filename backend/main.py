
# backend/main.py
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Body, Query, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import sqlite3, json, os
from io import BytesIO
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field
import logging

# ====== Cargar .env ======
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)
ADMIN_USER = os.getenv("ADMIN_USER") or "admin"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or "Admin2025"
DB = os.getenv("DB_PATH") or "data.db"

app = FastAPI(title="Resemin App Backend", version="1.6.0")

# ====== CORS ======
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://resemin-portal.netlify.app",  # <--- tu dominio de Netlify
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ====== Logs ======
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("resemin")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"--> {request.method} {request.url}")
    try:
        response = await call_next(request)
        logger.info(f"<-- {response.status_code} {request.url}")
        return response
    except Exception:
        logger.exception("Excepción durante request")
        raise

# ====== DB init + migración ======
def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS employees(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS meta(
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS config(
        id INTEGER,
        dni TEXT,
        fecha TEXT,
        visibles TEXT
    )
    """)
    con.commit(); con.close()
    ensure_config_schema()

def ensure_config_schema():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("PRAGMA table_info(config)")
    cols = [row[1] for row in cur.fetchall()]
    if "id" not in cols:
        try:
            cur.execute("ALTER TABLE config ADD COLUMN id INTEGER")
            cur.execute("UPDATE config SET id=1 WHERE id IS NULL")
            con.commit()
        except Exception:
            cur.execute("CREATE TABLE IF NOT EXISTS config_new (id INTEGER, dni TEXT, fecha TEXT, visibles TEXT)")
            cur.execute("INSERT INTO config_new (id, dni, fecha, visibles) SELECT 1, dni, fecha, visibles FROM config")
            cur.execute("DROP TABLE config")
            cur.execute("ALTER TABLE config_new RENAME TO config")
            con.commit()
    con.close()

init_db()

# ====== Utilidades ======
def check_admin(user: Optional[str], pwd: Optional[str]):
    if not ADMIN_PASSWORD or not ADMIN_USER:
        raise HTTPException(status_code=500, detail="ADMIN_USER/PASSWORD no configurados")
    if user != ADMIN_USER or pwd != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

def to_iso_date(val):
    try:
        if isinstance(val, (pd.Timestamp, datetime, date)):
            return pd.to_datetime(val).strftime("%Y-%m-%d")
    except Exception:
        pass
    return val

def normalize_row(row_dict: dict) -> dict:
    out = {}
    for k, v in row_dict.items():
        nv = to_iso_date(v)
        out[str(k)] = nv if (nv is None or isinstance(nv, (str, int, float))) else str(nv)
    return out

def set_meta(key: str, value: str):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    con.commit(); con.close()

def get_meta(key: str) -> Optional[str]:
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT value FROM meta WHERE key=?", (key,))
    row = cur.fetchone(); con.close()
    return row[0] if row else None

def get_last_columns() -> List[str]:
    val = get_meta("columns")
    if val:
        try:
            cols = json.loads(val)
            if isinstance(cols, list):
                return [str(c) for c in cols]
        except Exception:
            pass
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT data FROM employees LIMIT 1")
    row = cur.fetchone(); con.close()
    if row:
        try:
            data = json.loads(row[0])
            return list(map(str, data.keys()))
        except Exception:
            return []
    return []

def get_config():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT dni, fecha, visibles FROM config WHERE id=1")
    row = cur.fetchone(); con.close()
    if not row:
        return None
    dni_col, fecha_col, visibles_json = row
    visibles = json.loads(visibles_json) if visibles_json else []
    return {"dni": dni_col, "fecha": fecha_col, "visibles": visibles}

def validate_columns_exist(dni_col: str, fecha_col: str, visibles: List[str], available: List[str]):
    missing = []
    for name in [dni_col, fecha_col] + (visibles or []):
        if name and name not in available:
            missing.append(name)
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Columnas no encontradas en el Excel cargado",
                "faltantes": missing,
                "disponibles": available
            }
        )

# ====== Importa mapeo flexible ======
from .excel_mapping import (
    dataframe_with_canonical_headers,
    # también puedes importar estas si las quieres usar en /config
    VISIBLE_DEFAULT,
)

# ====== Básicas ======
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "Resemin Backend activo", "docs": "/docs"}

@app.get("/config")
def config_endpoint():
    return {
        "allowed_origins": ALLOWED_ORIGINS,
        "version": "1.6.0",
    }

# ====== Login Admin ======
@app.post("/admin/login")
def admin_login(
    x_admin_user: Optional[str] = Header(None, alias="X-Admin-User"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
):
    check_admin(x_admin_user, x_admin_password)
    return {"ok": True, "message": "Login correcto"}

# ====== ADMIN: Upload (con mapeo flexible) ======
@app.post("/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    x_admin_user: Optional[str] = Header(None, alias="X-Admin-User"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
    # overrides opcionales desde Admin (si quieres usarlos ahora o más adelante)
    dni_col_original: Optional[str] = Form(None),
    fecha_col_original: Optional[str] = Form(None),
):
    check_admin(x_admin_user, x_admin_password)

    contents = await file.read()
    bio = BytesIO(contents)

    # Lee .xlsx preferentemente, cae a autodetección si falla
    try:
        df = pd.read_excel(bio, engine="openpyxl")
    except Exception:
        bio.seek(0)
        try:
            df = pd.read_excel(bio)  # .xls si xlrd está instalado
        except Exception as e2:
            raise HTTPException(status_code=400, detail=f"No se pudo leer el Excel. Usa .xlsx. Detalle: {e2}")

    # Admin puede forzar equivalencias, si decides enviar estos valores desde el front
    admin_map = {}
    if dni_col_original:
        admin_map[dni_col_original] = "TRABAJADOR"
    if fecha_col_original:
        admin_map[fecha_col_original] = "FECHA_INGRESO"

    # >>> Mapeo flexible y renombre a canónicos
    try:
        df_canon, header_map = dataframe_with_canonical_headers(df, admin_map)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    # Persistir filas (con cabeceras canónicas)
    rows = [normalize_row(r) for _, r in df_canon.iterrows()]
    columns = list(map(str, df_canon.columns))

    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("DELETE FROM employees")
    for r in rows:
        cur.execute("INSERT INTO employees(data) VALUES(?)", (json.dumps(r, ensure_ascii=False),))
    con.commit(); con.close()

    # Guardar columnas canónicas en meta
    set_meta("columns", json.dumps(columns, ensure_ascii=False))

    return {"columns": columns, "rows": len(rows), "mapeo_aplicado": header_map}

# ====== ADMIN: Config (JSON) ======
class ConfigPayload(BaseModel):
    dni_column: str = Field(..., description="Nombre de la columna DNI (canónica)")
    fecha_column: str = Field(..., description="Nombre de la columna Fecha (canónica)")
    visible_columns: List[str] = Field(..., description="Columnas visibles en consultas públicas (canónicas)")

@app.post("/admin/config")
def admin_config(
    payload: ConfigPayload = Body(..., media_type="application/json"),
    x_admin_user: Optional[str] = Header(None, alias="X-Admin-User"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
):
    check_admin(x_admin_user, x_admin_password)
    dni_column = payload.dni_column.strip()
    fecha_column = payload.fecha_column.strip()
    visible_columns = payload.visible_columns or []
    if not dni_column or not fecha_column or not visible_columns:
        raise HTTPException(status_code=400, detail="Completa DNI, Fecha y columnas visibles")

    # Ahora available son canónicas (las que guardamos en meta)
    available = get_last_columns()
    if not available:
        raise HTTPException(status_code=409, detail="No hay columnas cargadas aún. Primero suba el Excel en /admin/upload.")

    validate_columns_exist(dni_column, fecha_column, visible_columns, available)

    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("DELETE FROM config WHERE id=1")
    cur.execute(
        "INSERT INTO config(id, dni, fecha, visibles) VALUES(1, ?, ?, ?)",
        (dni_column, fecha_column, json.dumps(visible_columns, ensure_ascii=False))
    )
    con.commit(); con.close()

    return {"ok": True, "dni_column": dni_column, "fecha_column": fecha_column, "visible_columns": visible_columns}

@app.get("/admin/status")
def admin_status(
    x_admin_user: Optional[str] = Header(None, alias="X-Admin-User"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
):
    check_admin(x_admin_user, x_admin_password)
    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM employees")
    employees_count = cur.fetchone()[0]
    cfg = get_config()
    con.close()
    return {"employees": employees_count, "config": cfg}

# ====== Públicos ======
@app.post("/consulta")
def consulta(item: dict):
    cfg = get_config()
    if not cfg:
        raise HTTPException(status_code=400, detail="No configurado")
    dni_col = cfg["dni"]; fecha_col = cfg["fecha"]; visibles = cfg["visibles"]

    con = sqlite3.connect(DB); cur = con.cursor()
    cur.execute("SELECT data FROM employees")
    res = []
    for (row,) in cur.fetchall():
        data = json.loads(row)
        if str(data.get(dni_col, "")) == str(item.get("dni", "")) and str(data.get(fecha_col, "")) == str(item.get("fecha", "")):
            res.append({k: data.get(k) for k in visibles})
    con.close()
    return {"results": res}

@app.get("/public/columns")
def public_columns():
    cfg = get_config()
    if not cfg:
        raise HTTPException(status_code=404, detail="No hay configuración guardada")
    return {"visible_columns": cfg["visibles"]}

@app.get("/public/query")
def public_query(dni: str = Query(...), fecha: str = Query(...)):
    try:
        cfg = get_config()
        if not cfg:
            return {"found": False, "message": "No hay configuración guardada"}
        dni_col = cfg["dni"]; fecha_col = cfg["fecha"]; visibles = cfg["visibles"]
        available = get_last_columns()
        validate_columns_exist(dni_col, fecha_col, visibles, available)

        con = sqlite3.connect(DB); cur = con.cursor()
        cur.execute("SELECT data FROM employees")
        for (row,) in cur.fetchall():
            data = json.loads(row)
            if str(data.get(dni_col, "")) == str(dni) and str(data.get(fecha_col, "")) == str(fecha):
                con.close()
                return {"found": True, "data": {k: data.get(k) for k in visibles}}
        con.close()
        return {"found": False, "message": "No se encontró registro para ese DNI y fecha"}
    except HTTPException as he:
        raise he
    except Exception as e:
        return {"found": False, "message": f"Error interno: {str(e)}"}
