"""
Guatecompras Alert Monitor
Descarga concursos nuevos del MINFIN, filtra por palabras clave
y manda alertas por email a clientes suscritos.
"""

import requests
import pandas as pd
import sqlite3
import smtplib
import json
import logging
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ─── Configuración ────────────────────────────────────────────────────────────

# Resend API key (obtén una gratis en resend.com)
RESEND_API_KEY = "re_XXXXXXXXXXXXXXXXXXXXXXXX"

# Email desde el que mandas (debe estar verificado en Resend)
FROM_EMAIL = "alertas@tudominio.com"
FROM_NAME  = "Monitor Guatecompras"

# URL de datos abiertos MINFIN — concursos activos 2026
# Cambia el UUID según el año en: datos.minfin.gob.gt
DATA_URLS = [
    # Concursos 2026 adjudicados (más recientes)
    "https://datosabiertos.minfin.gob.gt/api/DatosAbiertos/Descargar/concurso-guatecompras-2016-a-2026/concursos-2026-adjudicados.xlsx",
    # Fallback: buscar directamente en Guatecompras
]

DB_PATH   = Path("data/alertas.db")
LOG_PATH  = Path("logs/monitor.log")

# ─── Clientes ────────────────────────────────────────────────────────────────

# Agrega aquí a tus clientes con sus palabras clave
CLIENTES = [
    {
        "nombre": "Ferretería El Constructor",
        "email":  "gerente@constructorgt.com",
        "keywords": ["ferretería", "ferreteria", "materiales de construcción",
                     "pintura", "cemento", "hierro", "herramientas"]
    },
    {
        "nombre": "TechSoluciones GT",
        "email":  "ventas@techsoluciones.gt",
        "keywords": ["computadoras", "laptop", "servidor", "software",
                     "tecnología", "informatica", "equipos de computo",
                     "mantenimiento de equipo"]
    },
    {
        "nombre": "Servicios de Limpieza Brillante",
        "email":  "admin@brillantegt.com",
        "keywords": ["limpieza", "aseo", "jardinería", "jardineria",
                     "mantenimiento de instalaciones", "fumigación"]
    },
]

# ─── Logging ──────────────────────────────────────────────────────────────────

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

# ─── Base de datos ────────────────────────────────────────────────────────────

def init_db():
    """Crea la tabla si no existe."""
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS alertas_enviadas (
            nog         TEXT,
            cliente_email TEXT,
            enviado_el  TEXT,
            PRIMARY KEY (nog, cliente_email)
        )
    """)
    con.commit()
    return con

def ya_notificado(con, nog: str, email: str) -> bool:
    cur = con.execute(
        "SELECT 1 FROM alertas_enviadas WHERE nog=? AND cliente_email=?",
        (nog, email)
    )
    return cur.fetchone() is not None

def marcar_notificado(con, nog: str, email: str):
    con.execute(
        "INSERT OR IGNORE INTO alertas_enviadas VALUES (?,?,?)",
        (nog, email, datetime.now().isoformat())
    )
    con.commit()

# ─── Descarga de concursos ────────────────────────────────────────────────────

def descargar_concursos_minfin() -> pd.DataFrame | None:
    """
    Intenta descargar datos del portal de datos abiertos del MINFIN.
    Retorna un DataFrame con los concursos o None si falla.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AlertaGuatecompras/1.0)"}

    # Endpoint alternativo con parámetros de fecha
    url = "https://datosabiertos.minfin.gob.gt/api/DatosAbiertos/Descargar/concurso-guatecompras-2016-a-2026/40151f4e-4c16-4f18-8c24-cc22a95624f8.xlsx"

    try:
        log.info(f"Descargando datos de MINFIN...")
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()

        # Guardar xlsx temporal
        tmp = Path("data/concursos_tmp.xlsx")
        tmp.write_bytes(r.content)

        df = pd.read_excel(tmp, engine="openpyxl")
        log.info(f"Descargados {len(df)} concursos del MINFIN")
        return df

    except Exception as e:
        log.warning(f"MINFIN falló: {e}")
        return None


def descargar_concursos_guatecompras() -> pd.DataFrame | None:
    """
    Fallback: scrape directo de guatecompras.gt
    usando la búsqueda avanzada con parámetros GET simples.
    """
    import io
    from datetime import timedelta

    hoy = date.today()
    ayer = hoy - timedelta(days=1)

    # Guatecompras tiene una vista exportable en algunos endpoints
    url = "https://www.guatecompras.gt/concursos/listadoconcursos.aspx"
    params = {
        "e": "1",   # estado: vigente
        "fp": ayer.strftime("%d/%m/%Y"),
        "fs": hoy.strftime("%d/%m/%Y"),
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-GT,es;q=0.9",
    }

    try:
        log.info("Intentando scrape directo de Guatecompras...")
        r = requests.get(url, params=params, headers=headers, timeout=20)

        # Parsear HTML con pandas (busca tablas)
        tablas = pd.read_html(io.StringIO(r.text))
        if tablas:
            df = tablas[0]
            log.info(f"Scrape directo: {len(df)} filas encontradas")
            return df

    except Exception as e:
        log.warning(f"Scrape directo falló: {e}")

    return None

# ─── Filtrado ─────────────────────────────────────────────────────────────────

def filtrar_para_cliente(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    """Filtra filas donde alguna columna de texto contenga alguna keyword."""
    mask = pd.Series([False] * len(df))

    # Columnas donde buscar (ajusta según la estructura real del excel del MINFIN)
    columnas_texto = [c for c in df.columns if df[c].dtype == object]

    for col in columnas_texto:
        for kw in keywords:
            coincide = df[col].fillna("").str.lower().str.contains(
                kw.lower(), na=False, regex=False
            )
            mask = mask | coincide

    return df[mask].copy()


def extraer_nog(fila: pd.Series) -> str:
    """Intenta extraer el NOG (número de operación) de la fila."""
    for col in ["NOG", "nog", "Número", "Numero", "N° Operación", "NumeroOperacion"]:
        if col in fila.index and pd.notna(fila[col]):
            return str(fila[col]).strip()
    # Fallback: hash de la fila completa
    return str(hash(tuple(fila.values)))


def extraer_descripcion(fila: pd.Series) -> str:
    for col in ["Descripción", "Descripcion", "Nombre", "Objeto", "Detalle", "DESCRIPCION"]:
        if col in fila.index and pd.notna(fila[col]):
            return str(fila[col]).strip()
    return "Sin descripción"


def extraer_entidad(fila: pd.Series) -> str:
    for col in ["Entidad", "Unidad Compradora", "Institución", "ENTIDAD"]:
        if col in fila.index and pd.notna(fila[col]):
            return str(fila[col]).strip()
    return "No especificada"


def extraer_monto(fila: pd.Series) -> str:
    for col in ["Monto", "Valor", "Presupuesto", "MONTO", "Total"]:
        if col in fila.index and pd.notna(fila[col]):
            try:
                val = float(str(fila[col]).replace(",", "").replace("Q", ""))
                return f"Q{val:,.2f}"
            except:
                return str(fila[col])
    return "No indicado"


def extraer_fecha_cierre(fila: pd.Series) -> str:
    for col in ["Fecha Cierre", "Fecha de Cierre", "Vencimiento", "FECHA_CIERRE"]:
        if col in fila.index and pd.notna(fila[col]):
            return str(fila[col]).strip()
    return "Consultar en Guatecompras"

# ─── Email ────────────────────────────────────────────────────────────────────

def construir_html_alerta(cliente_nombre: str, concursos: list[dict]) -> str:
    filas = ""
    for c in concursos:
        nog = c.get("nog", "N/A")
        link = f"https://www.guatecompras.gt/concursos/consultaConNOG.aspx?NOG={nog}"
        filas += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:12px 8px;font-size:14px">{c['descripcion']}</td>
          <td style="padding:12px 8px;font-size:13px;color:#555">{c['entidad']}</td>
          <td style="padding:12px 8px;font-size:13px;font-weight:600;color:#1a7a4a">{c['monto']}</td>
          <td style="padding:12px 8px;font-size:13px">{c['fecha_cierre']}</td>
          <td style="padding:12px 8px">
            <a href="{link}" style="background:#1a7a4a;color:#fff;padding:6px 14px;border-radius:4px;text-decoration:none;font-size:12px">Ver NOG {nog}</a>
          </td>
        </tr>"""

    return f"""
    <!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;color:#333">
      <div style="background:#1a7a4a;padding:20px;border-radius:8px 8px 0 0">
        <h1 style="color:#fff;margin:0;font-size:22px">🔔 Nuevas Licitaciones Detectadas</h1>
        <p style="color:#a8d5bc;margin:6px 0 0">Reporte del {date.today().strftime('%d/%m/%Y')}</p>
      </div>
      <div style="background:#f9f9f9;padding:16px 20px;border:1px solid #ddd">
        <p style="margin:0">Hola <strong>{cliente_nombre}</strong>, encontramos <strong>{len(concursos)} licitación(es) nuevas</strong> que coinciden con tu rubro:</p>
      </div>
      <table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #ddd">
        <thead>
          <tr style="background:#f0f0f0">
            <th style="padding:10px 8px;text-align:left;font-size:13px">Descripción</th>
            <th style="padding:10px 8px;text-align:left;font-size:13px">Entidad</th>
            <th style="padding:10px 8px;text-align:left;font-size:13px">Monto</th>
            <th style="padding:10px 8px;text-align:left;font-size:13px">Cierre</th>
            <th style="padding:10px 8px;text-align:left;font-size:13px">Enlace</th>
          </tr>
        </thead>
        <tbody>{filas}</tbody>
      </table>
      <div style="padding:16px 20px;background:#fff;border:1px solid #ddd;border-top:none;font-size:12px;color:#888">
        Recibes este correo porque estás suscrito al Monitor de Licitaciones Guatecompras.<br>
        Para cambiar tus palabras clave o cancelar, responde este correo.
      </div>
    </body></html>"""


def enviar_email_resend(to_email: str, to_name: str, html: str, num_concursos: int):
    """Envía el email usando la API de Resend (resend.com)."""
    payload = {
        "from": f"{FROM_NAME} <{FROM_EMAIL}>",
        "to": [to_email],
        "subject": f"🔔 {num_concursos} licitación(es) nueva(s) en tu rubro — {date.today().strftime('%d/%m/%Y')}",
        "html": html,
    }
    r = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )
    r.raise_for_status()
    log.info(f"Email enviado a {to_email} — ID: {r.json().get('id')}")

# ─── Pipeline principal ───────────────────────────────────────────────────────

def main():
    log.info("=== Iniciando Monitor Guatecompras ===")
    con = init_db()

    # 1. Descargar concursos
    df = descargar_concursos_minfin()
    if df is None:
        df = descargar_concursos_guatecompras()
    if df is None:
        log.error("No se pudo obtener datos. Abortando.")
        return

    log.info(f"Columnas disponibles: {list(df.columns)}")

    # 2. Para cada cliente, filtrar y notificar
    for cliente in CLIENTES:
        log.info(f"Procesando cliente: {cliente['nombre']}")
        matches = filtrar_para_cliente(df, cliente["keywords"])

        if matches.empty:
            log.info(f"  → Sin coincidencias para {cliente['nombre']}")
            continue

        # 3. Descartar los que ya notificamos
        nuevos = []
        for _, fila in matches.iterrows():
            nog = extraer_nog(fila)
            if ya_notificado(con, nog, cliente["email"]):
                continue
            nuevos.append({
                "nog":          nog,
                "descripcion":  extraer_descripcion(fila),
                "entidad":      extraer_entidad(fila),
                "monto":        extraer_monto(fila),
                "fecha_cierre": extraer_fecha_cierre(fila),
            })

        if not nuevos:
            log.info(f"  → Todo ya notificado para {cliente['nombre']}")
            continue

        log.info(f"  → {len(nuevos)} concurso(s) nuevo(s) para {cliente['nombre']}")

        # 4. Enviar email
        html = construir_html_alerta(cliente["nombre"], nuevos)
        try:
            enviar_email_resend(cliente["email"], cliente["nombre"], html, len(nuevos))
            # 5. Marcar como notificados
            for c in nuevos:
                marcar_notificado(con, c["nog"], cliente["email"])
        except Exception as e:
            log.error(f"  ✗ Error enviando email a {cliente['email']}: {e}")

    con.close()
    log.info("=== Monitor finalizado ===")


if __name__ == "__main__":
    main()
