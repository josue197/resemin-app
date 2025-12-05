
# backend/excel_mapping.py
# ===========================================
#  Mapeo flexible de cabeceras de Excel
#  - Normaliza (mayúsculas, sin acentos, " " y "." -> "_")
#  - Alias (sinónimos frecuentes)
#  - Fuzzy matching (coincidencia aproximada)
#  - Valida campos mínimos
# ===========================================
import unicodedata
import difflib
import pandas as pd
from typing import List, Dict, Set, Tuple

# Campos canónicos que el backend entiende (ajústalos si cambias tu modelo)
CANONICAL_FIELDS: Set[str] = {
    "DESCRIPCION_EMPRESA",
    "CODIGO_UNIDAD",
    "DESCRIPCION_UNIDAD",
    "NOMBRE",
    "TRABAJADOR",           # DNI
    "APELLIDOS_NOMBRES",
    "FECHA_INGRESO",
    "FECHA_CESE",
    "SITUACION_TRABAJADOR",
    "PERIODO_VACACIONAL",
    "DIAS_PENDIENTES",
    "IND_DIAS",
    "SALDO_IND_DIAS",
    "VALORIZACION",
    "VALORIZACION_IND",
    "OBSERVACION",
}

# Alias frecuentes (incluye tus cabeceras nuevas)
COLUMN_ALIASES: Dict[str, str] = {
    # Empresa / Unidad
    "EMPRESA": "DESCRIPCION_EMPRESA",
    "DESCRIPCION EMPRESA": "DESCRIPCION_EMPRESA",
    "COD_EMPRESA": "CODIGO_UNIDAD",
    "CODIGO UNIDAD": "CODIGO_UNIDAD",
    "DESCRIPCION UNIDAD": "DESCRIPCION_UNIDAD",

    # Persona
    "NOMBRES": "NOMBRE",
    "APELLIDOS Y NOMBRES": "APELLIDOS_NOMBRES",
    "APELLIDOS_NOMBRES": "APELLIDOS_NOMBRES",
    "DNI": "TRABAJADOR",
    "TRABAJADOR": "TRABAJADOR",

    # Fechas
    "FECHA INGRESO": "FECHA_INGRESO",
    "FEC_INGRESO": "FECHA_INGRESO",
    "FECHA DE CESE": "FECHA_CESE",
    "FEC_CESE": "FECHA_CESE",

    # Estado / indicadores / valores
    "SITUACIÓN TRABAJADOR": "SITUACION_TRABAJADOR",
    "SITUACION_TRABAJADOR": "SITUACION_TRABAJADOR",
    "PERIODO VACACIONAL": "PERIODO_VACACIONAL",
    "PERIODO_VACACIONAL": "PERIODO_VACACIONAL",
    "DIAS_PENDIENTES": "DIAS_PENDIENTES",
    "SALDO IND. DIAS": "SALDO_IND_DIAS",
    "SALDO IND DIAS": "SALDO_IND_DIAS",
    "VALORIZACION": "VALORIZACION",
    "VALORIZACION IND.": "VALORIZACION_IND",
    "VALORIZACION IND": "VALORIZACION_IND",
    "OBSERVACION": "OBSERVACION",
}

# Campos mínimos para que la consulta funcione
REQUIRED_CORE: Set[str] = {"TRABAJADOR", "FECHA_INGRESO"}

# Sugerencia de columnas visibles por defecto
VISIBLE_DEFAULT: List[str] = [
    "DESCRIPCION_EMPRESA", "NOMBRE", "APELLIDOS_NOMBRES",
    "FECHA_INGRESO", "FECHA_CESE", "SITUACION_TRABAJADOR",
    "PERIODO_VACACIONAL", "DIAS_PENDIENTES", "SALDO_IND_DIAS",
    "VALORIZACION", "VALORIZACION_IND", "OBSERVACION",
]

def strip_accents(s: str) -> str:
    """Quita acentos y diacríticos."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )

def normalize_header(raw: str) -> str:
    """
    Normaliza: trim, quita acentos, mayúsculas,
    reemplaza '.', '-', múltiples espacios por '_'.
    Ej: 'Saldo Ind. Dias' -> 'SALDO_IND_DIAS'
    """
    s = str(raw).strip()
    s = strip_accents(s)
    s = s.replace(".", " ").replace("-", " ")
    s = "_".join(s.split())
    return s.upper()

def build_header_map(found_cols: List[str]) -> Dict[str, str]:
    """
    Crea {col_original → col_canonica}:
    - Alias directos (con y sin normalización)
    - Canónicos exactos
    - Fuzzy matching para lo restante
    """
    mapping: Dict[str, str] = {}
    FUZZY_THRESHOLD = 0.78  # tolerante pero razonable

    # 1) Alias y canónicos exactos
    for c in found_cols:
        norm = normalize_header(c)
        if c in COLUMN_ALIASES:
            mapping[c] = COLUMN_ALIASES[c]
        elif norm in COLUMN_ALIASES:
            mapping[c] = COLUMN_ALIASES[norm]
        elif norm in CANONICAL_FIELDS:
            mapping[c] = norm

    # 2) Fuzzy para lo que falte
    for c in found_cols:
        if c in mapping:
            continue
        norm = normalize_header(c)
        best = difflib.get_close_matches(norm, list(CANONICAL_FIELDS), n=1, cutoff=FUZZY_THRESHOLD)
        if best:
            mapping[c] = best[0]

    return mapping

def dataframe_with_canonical_headers(df: pd.DataFrame, admin_map: Dict[str, str] | None = None) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """
    Renombra el DataFrame a canónicos y valida mínimos.
    admin_map permite forzar mapeos (ej.: {"DNI":"TRABAJADOR"}).
    """
    found_cols = list(df.columns)
    auto_map = build_header_map(found_cols)
    header_map = dict(auto_map or {})
    if admin_map:
        header_map.update(admin_map)

    df = df.rename(columns=header_map)

    # Validar mínimos
    mapped_targets = set(header_map.values())
    missing_core = [r for r in REQUIRED_CORE if r not in mapped_targets]
    if missing_core:
        raise ValueError(
            f"Faltan columnas esenciales tras el mapeo: {missing_core}. "
            f"Encontradas: {found_cols}. Mapeo aplicado: {header_map}"
        )

    # Rellenar opcionales faltantes con NaN para que el pipeline no falle
    for c in CANONICAL_FIELDS:
        if c not in df.columns:
            df[c] = pd.NA

    # Formato de fechas
    for date_col in ["FECHA_INGRESO", "FECHA_CESE"]:
        if date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

    return df, header_map
