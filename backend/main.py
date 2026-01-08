
# backend/main.py
from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Body, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd
import json, os, math
from io import BytesIO
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field
import logging

# ==== SQLAlchemy (PostgreSQL / Supabase) ====
from sqlalchemy import create_engine, Column, Integer, String, Text, MetaData, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.dialects.postgresql import JSONB

# ====== Cargar .env (solo útil en local) ======
ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

ADMIN_USER = os.getenv("ADMIN_USER") or "admin"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or "Admin2025"
DATABASE_URL = os.getenv("DATABASE_URL")  # <-- usa Supabase; ya NO usamos DB_PATH

if not DATABASE_URL:
    # En Render debe estar seteada; si falta, lo advertimos
    print("⚠️  DATABASE_URL no está configurada en el entorno. Configúrala en Render.")

# SQLAlchemy setup
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False) if engine else None
Base = declarative_base(metadata=MetaData())

# Tablas: reemplazan employees/meta/config de SQLite con tipos Postgres
class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    data = Column(JSONB, nullable=False)  # fila completa del Excel como JSONB

class MetaEntry(Base):
    __tablename__ = "meta"
    key = Column(String, primary_key=True)
    value = Column(Text)  # guardaremos JSON en texto (p.ej. columnas)

class Config(Base):
    __tablename__ = "config"
    id = Column(Integer, primary_key=True, index=True)
    dni = Column(String)       # nombre de columna DNI
    fecha = Column(String)     # nombre de columna FECHA (elige "FECHA NACIMIENTO")
    visibles = Column(JSONB)   # lista de columnas visibles (JSON)

def init_db():
    if engine is None:
        return
    Base.metadata.create_all(bind=engine)

# ====== FastAPI ======
app = FastAPI(title="Resemin App Backend", version="1.9.0")

# ====== CORS ======
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://resemin-portal.netlify.app",  # <-- tu dominio de Netlify
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

# ====== DB Session helper ======
def get_db() -> Session:
    if SessionLocal is None:
        raise HTTPException(status_code=500, detail="DATABASE_URL no configurado en el servidor.")
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # el cierre lo hacemos manual donde corresponda

# ====== Helpers para JSON y fechas ======
def is_null_like(v) -> bool:
    """True para None, NaN, NaT, pd.NA."""
    try:
        return pd.isna(v)  # cubre NaN, NaT, None y pd.NA
    except Exception:
        return v is None or (isinstance(v, float) and math.isnan(v))

def parse_input_date(s: str) -> str:
    """
    Acepta 'DD/MM/YYYY' o 'YYYY-MM-DD' y devuelve ISO 'YYYY-MM-DD'.
    Si no puede parsear, devuelve el string original.
    """
    if not s:
        return s
    try:
        return pd.to_datetime(s, format="%d/%m/%Y").strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        return pd.to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return s

def to_json_scalar(v):
    """
    Convierte cualquier valor a un escalar JSON seguro:
    - NaN/NaT/pd.NA -> None
    - Timestamps/fechas -> ISO 'YYYY-MM-DD'
    - Otros tipos -> tal cual o str si es no serializable
    """
    if is_null_like(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        try:
            return pd.to_datetime(v).strftime("%Y-%m-%d")
        except Exception:
            return None
    try:
        if hasattr(v, "item"):
            return v.item()  # numpy/pandas escalar -> python escalar
    except Exception:
        pass
    if isinstance(v, (dict, list, tuple, set)):
        try:
            return json.loads(json.dumps(v, default=str))
        except Exception:
            return str(v)
    return v

def normalize_row(row_dict: dict) -> dict:
    """Normaliza cada valor a algo JSON-compliant (sin NaN)."""
    out = {}
    for k, v in row_dict.items():
        out[str(k)] = to_json_scalar(v)
    return out

# ====== Seguridad Admin ======
def check_admin(user: Optional[str], pwd: Optional[str]):
    if not ADMIN_PASSWORD or not ADMIN_USER:
        raise HTTPException(status_code=500, detail="ADMIN_USER/PASSWORD no configurados")
    if user != ADMIN_USER or pwd != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ====== Meta helpers (PostgreSQL) ======
def set_meta(db: Session, key: str, value: str):
    entry = db.query(MetaEntry).filter(MetaEntry.key == key).first()
    if entry:
        entry.value = value
    else:
        entry = MetaEntry(key=key, value=value)
        db.add(entry)
    db.commit()

def get_meta(db: Session, key: str) -> Optional[str]:
    entry = db.query(MetaEntry).filter(MetaEntry.key == key).first()
    return entry.value if entry else None

def get_last_columns(db: Session) -> List[str]:
    val = get_meta(db, "columns")
    if val:
        try:
            cols = json.loads(val)
            if isinstance(cols, list):
                return [str(c) for c in cols]
        except Exception:
            pass
    # Si no hay meta, intenta leer de la primera fila
    first = db.query(Employee).first()
    if first and first.data:
        try:
            return list(map(str, first.data.keys()))
        except Exception:
            return []
    return []

def get_config(db: Session):
    cfg = db.query(Config).filter(Config.id == 1).first()
    if not cfg:
        return None
    visibles = cfg.visibles if isinstance(cfg.visibles, list) else []
    return {"dni": cfg.dni, "fecha": cfg.fecha, "visibles": visibles}

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
        "version": "1.9.0",
    }

# Inicializa DB al levantar
init_db()

# ====== Login Admin ======
@app.post("/admin/login")
def admin_login(
    x_admin_user: Optional[str] = Header(None, alias="X-Admin-User"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
):
    check_admin(x_admin_user, x_admin_password)
    return {"ok": True, "message": "Login correcto"}

# ====== ADMIN: Upload ======
@app.post("/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    x_admin_user: Optional[str] = Header(None, alias="X-Admin-User"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
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

    rows = [normalize_row(r) for _, r in df.iterrows()]
    columns = list(map(str, df.columns))

    db = get_db()
    try:
        # "Último Excel manda": limpiar empleados previos
        db.query(Employee).delete()
        db.commit()

        # Insertar filas
        for r in rows:
            db.add(Employee(data=r))
        db.commit()

        # Guardar meta: columnas
        set_meta(db, "columns", json.dumps(columns, ensure_ascii=False))

        return {"columns": columns, "rows": len(rows)}
    finally:
        db.close()

# ====== ADMIN: Config (JSON) ======
class ConfigPayload(BaseModel):
    dni_column: str = Field(..., description="Nombre de la columna DNI")
    fecha_column: str = Field(..., description="Nombre de la columna Fecha (ej. 'FECHA NACIMIENTO')")
    visible_columns: List[str] = Field(..., description="Columnas visibles en consultas públicas")

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

    db = get_db()
    try:
        available = get_last_columns(db)
        if not available:
            raise HTTPException(status_code=409, detail="No hay columnas cargadas aún. Primero suba el Excel en /admin/upload.")
        validate_columns_exist(dni_column, fecha_column, visible_columns, available)

        # Guarda/actualiza Config con id=1
        cfg = db.query(Config).filter(Config.id == 1).first()
        if not cfg:
            cfg = Config(id=1, dni=dni_column, fecha=fecha_column, visibles=visible_columns)
            db.add(cfg)
        else:
            cfg.dni = dni_column
            cfg.fecha = fecha_column
            cfg.visibles = visible_columns
        db.commit()

        return {"ok": True, "dni_column": dni_column, "fecha_column": fecha_column, "visible_columns": visible_columns}
    finally:
        db.close()

@app.get("/admin/status")
def admin_status(
    x_admin_user: Optional[str] = Header(None, alias="X-Admin-User"),
    x_admin_password: Optional[str] = Header(None, alias="X-Admin-Password"),
):
    check_admin(x_admin_user, x_admin_password)
    db = get_db()
    try:
        employees_count = db.query(Employee).count()
        cfg = get_config(db)
        return {"employees": employees_count, "config": cfg}
    finally:
        db.close()

# ====== Públicos ======
@app.post("/consulta")
def consulta(item: dict):
    """
    Consulta pública usando POST. Devuelve lista de coincidencias (varios periodos).
    Filtra por DNI y por la columna configurada como Fecha (usa parse_input_date).
    """
    db = get_db()
    try:
        cfg = get_config(db)
        if not cfg:
            raise HTTPException(status_code=400, detail="No configurado")
        dni_col = cfg["dni"]; fecha_col = cfg["fecha"]; visibles = cfg["visibles"]

        available = get_last_columns(db)
        validate_columns_exist(dni_col, fecha_col, visibles, available)

        # Normaliza la fecha del payload (acepta DD/MM/YYYY o ISO)
        req_dni = str(item.get("dni", "")).strip()
        req_fecha = parse_input_date(str(item.get("fecha", "")).strip())

        # Consulta eficiente en JSONB (PostgreSQL/Supabase)
        sql = text(f"""
            SELECT data
            FROM employees
            WHERE data->>'{dni_col}' = :dni
              AND data->>'{fecha_col}' = :fecha
        """)
        rows = db.execute(sql, {"dni": req_dni, "fecha": req_fecha}).fetchall()

        res = []
        for row in rows:
            data = row[0] or {}
            res.append({k: to_json_scalar(data.get(k)) for k in visibles})

        return {"results": res}
    finally:
        db.close()

@app.get("/public/columns")
def public_columns():
    db = get_db()
    try:
        cfg = get_config(db)
        if not cfg:
            raise HTTPException(status_code=404, detail="No hay configuración guardada")
        return {"visible_columns": cfg["visibles"]}
    finally:
        db.close()

@app.get("/public/query")
def public_query(dni: str = Query(...), fecha: str = Query(...)):
    """
    Consulta pública usando GET (parámetros en URL). Devuelve lista de coincidencias (varios periodos).
    Filtra por DNI y por la columna configurada como Fecha (usa parse_input_date).
    """
    db = get_db()
    try:
        cfg = get_config(db)
        if not cfg:
            return {"found": False, "message": "No hay configuración guardada"}
        dni_col = cfg["dni"]; fecha_col = cfg["fecha"]; visibles = cfg["visibles"]

        available = get_last_columns(db)
        validate_columns_exist(dni_col, fecha_col, visibles, available)

        # Normaliza fecha del query param
        req_dni = str(dni).strip()
        req_fecha = parse_input_date(str(fecha).strip())

        # Consulta eficiente en JSONB (PostgreSQL/Supabase)
        sql = text(f"""
            SELECT data
            FROM employees
            WHERE data->>'{dni_col}' = :dni
              AND data->>'{fecha_col}' = :fecha
        """)
        rows = db.execute(sql, {"dni": req_dni, "fecha": req_fecha}).fetchall()

        matches = []
        for row in rows:
            data = row[0] or {}
            matches.append({k: to_json_scalar(data.get(k)) for k in visibles})

        if matches:
            return {"found": True, "results": matches}
        else:
            return {"found": False, "message": "No se encontró registro para ese DNI y fecha"}
    except HTTPException as he:
        raise he
    except Exception as e:
        return {"found": False, "message": f"Error interno: {str(e)}"}
    finally:
        db.close()