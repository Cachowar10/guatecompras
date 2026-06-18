"""
Guatecompras → Google Sheets
Descarga el ZIP del mes actual, descomprime, filtra licitaciones de HOY
y las sube a Google Sheets para que Make las procese.
"""

import requests
import pandas as pd
import zipfile
import io
import json
import logging
from datetime import date
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# ─── Configuración ────────────────────────────────────────────────────────────

SPREADSHEET_ID = "1fUCa7DFnlTBHO6hKg4hB_M_yUoQOZxATxWEXVRYy10U"
SHEET_NAME     = "LICITACIONES HOY"
CREDENTIALS_FILE = "credentials.json"  # El JSON que descargaste de Google Cloud

LOG_PATH = Path("logs/sheets_sync.log")
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─── Descarga y descompresión ─────────────────────────────────────────────────

def descargar_csv_mes() -> pd.DataFrame | None:
    hoy = date.today()
    url = f"https://ocds.guatecompras.gt/file/csv/{hoy.year}/{hoy.month}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    log.info(f"Descargando ZIP de Guatecompras: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        log.info(f"ZIP descargado: {len(r.content)/1024/1024:.1f} MB")
        
        # Descomprimir en memoria
        z = zipfile.ZipFile(io.BytesIO(r.content))
        archivos = z.namelist()
        log.info(f"Archivos en ZIP: {archivos}")
        
        # Buscar el archivo de items (tiene las descripciones)
        archivo_items = next(
            (f for f in archivos if "ten_items" in f.lower()), None
        )
        if not archivo_items:
            # Fallback: usar records.csv
            archivo_items = next(
                (f for f in archivos if "records" in f.lower()), None
            )
        
        if not archivo_items:
            log.error(f"No se encontró archivo de items. Disponibles: {archivos}")
            return None
        
        log.info(f"Usando archivo: {archivo_items}")
        df = pd.read_csv(z.open(archivo_items), low_memory=False, encoding='latin-1')
        log.info(f"Total filas: {len(df)}, Columnas: {list(df.columns[:8])}")
        return df
        
    except Exception as e:
        log.error(f"Error descargando ZIP: {e}")
        return None

# ─── Filtrar por fecha de hoy ─────────────────────────────────────────────────

def filtrar_hoy(df: pd.DataFrame) -> pd.DataFrame:
    hoy = date.today().isoformat()  # "2026-06-17"
    
    # Buscar columna de fecha
    col_fecha = None
    for col in df.columns:
        if "date" in col.lower() or "fecha" in col.lower():
            col_fecha = col
            break
    
    if not col_fecha:
        # Buscar en compiledRelease/id que tiene la fecha embebida
        col_fecha = next(
            (c for c in df.columns if "compiledRelease/id" in c), None
        )
    
    if col_fecha:
        log.info(f"Filtrando por columna: {col_fecha}")
        mask = df[col_fecha].fillna("").astype(str).str.contains(hoy, na=False)
        resultado = df[mask].copy()
        log.info(f"Licitaciones de hoy ({hoy}): {len(resultado)}")
        return resultado
    else:
        log.warning("No se encontró columna de fecha, devolviendo todas las filas")
        return df

# ─── Subir a Google Sheets ────────────────────────────────────────────────────

def subir_a_sheets(df: pd.DataFrame):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    
    # Limpiar hoja antes de subir
    sheet.clear()
    
    if df.empty:
        log.info("No hay licitaciones nuevas hoy.")
        sheet.append_row(["Sin licitaciones nuevas hoy", "", "", "", ""])
        return
    
    # Extraer columnas relevantes
    def get_col(df, *names):
        for name in names:
            if name in df.columns:
                return df[name].fillna("").astype(str)
        return pd.Series([""] * len(df))
    
    fecha_col      = get_col(df, "compiledRelease/id", "date")
    nog_col        = get_col(df, "compiledRelease/tender/id")
    desc_col       = get_col(df, "compiledRelease/tender/items/0/description")
    entidad_col    = get_col(df, "compiledRelease/buyer/name", "compiledRelease/tender/procuringEntity/name")
    
    # Header
    rows = [["fecha", "nog", "descripcion", "entidad", "link"]]
    
    for i in range(len(df)):
        nog  = nog_col.iloc[i]
        link = f"https://www.guatecompras.gt/concursos/consultaConNOG.aspx?NOG={nog.replace('GT-NOG-', '')}" if nog else ""
        rows.append([
            fecha_col.iloc[i][:10],  # Solo fecha YYYY-MM-DD
            nog,
            desc_col.iloc[i],
            entidad_col.iloc[i],
            link
        ])
    
    sheet.update(rows, "A1")
    log.info(f"✓ {len(df)} licitaciones subidas a Google Sheets")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("=== Iniciando sincronización Guatecompras → Sheets ===")
    
    df = descargar_csv_mes()
    if df is None:
        log.error("No se pudo descargar datos. Abortando.")
        return
    
    df_hoy = filtrar_hoy(df)
    subir_a_sheets(df_hoy)
    
    log.info("=== Sincronización completada ===")

if __name__ == "__main__":
    main()
