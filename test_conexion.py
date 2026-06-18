"""
Corre este script primero para verificar que todo funciona desde tu PC.
Prueba la conexión a Guatecompras y muestra las columnas disponibles.
"""

import requests
import pandas as pd
import io

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'es-GT,es;q=0.9',
}

session = requests.Session()
session.headers.update(headers)

print("="*50)
print("TEST 1: Conexión a Guatecompras")
print("="*50)

try:
    # Cargar home primero para obtener cookies
    r = session.get('https://www.guatecompras.gt/', timeout=15)
    print(f"✓ Home: {r.status_code}")

    # Ahora la lista de concursos
    r2 = session.get(
        'https://www.guatecompras.gt/concursos/listadoconcursos.aspx',
        params={'e': 1},  # e=1 = concursos vigentes
        timeout=15
    )
    print(f"✓ Lista concursos: {r2.status_code} ({len(r2.content)} bytes)")

    if r2.status_code == 200:
        tablas = pd.read_html(io.StringIO(r2.text))
        print(f"✓ Tablas encontradas: {len(tablas)}")
        for i, t in enumerate(tablas):
            print(f"\n  TABLA {i} — shape: {t.shape}")
            print(f"  Columnas: {list(t.columns)}")
            print(f"  Muestra:\n{t.head(3).to_string()}")

except Exception as e:
    print(f"✗ Error: {e}")

print("\n" + "="*50)
print("TEST 2: Datos Abiertos MINFIN")
print("="*50)

try:
    r = requests.get(
        'https://datosabiertos.minfin.gob.gt/api/DatosAbiertos/Descargar/concurso-guatecompras-2016-a-2026/40151f4e-4c16-4f18-8c24-cc22a95624f8.xlsx',
        headers=headers,
        timeout=30
    )
    print(f"MINFIN status: {r.status_code} ({len(r.content)} bytes)")

    if r.status_code == 200:
        df = pd.read_excel(io.BytesIO(r.content), engine='openpyxl')
        print(f"✓ Filas: {len(df)}, Columnas: {list(df.columns)}")
        print(f"Muestra:\n{df.head(3).to_string()}")

except Exception as e:
    print(f"✗ Error MINFIN: {e}")
