# Monitor de Licitaciones Guatecompras 🇬🇹

Manda alertas automáticas por email cuando aparecen licitaciones nuevas en el rubro de cada cliente.

---

## Instalación (tu PC, 10 minutos)

```bash
# 1. Clonar / copiar la carpeta del proyecto
cd guatecompras-alertas

# 2. Crear entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Probar conexión
python test_conexion.py
```

---

## Configuración rápida

Abre `monitor.py` y edita estas secciones:

### 1. Tu API key de Resend
```python
RESEND_API_KEY = "re_XXXXXXX"   # Obtén una gratis en resend.com
FROM_EMAIL     = "alertas@tudominio.com"
```

### 2. Agregar clientes
```python
CLIENTES = [
    {
        "nombre":   "Nombre del negocio",
        "email":    "correo@cliente.com",
        "keywords": ["palabra1", "palabra2", "palabra3"]
    },
    # ... más clientes
]
```

**Keywords recomendadas por rubro:**
- Ferretería: `ferretería, materiales construcción, pintura, cemento, hierro`
- TI: `computadoras, software, servidor, mantenimiento de equipo, informática`
- Limpieza: `limpieza, aseo, fumigación, mantenimiento de instalaciones`
- Seguridad: `seguridad, vigilancia, guardianía`
- Papelería: `papelería, útiles de oficina, suministros`

---

## Correr el monitor

```bash
# Manual (prueba)
python monitor.py

# Ver el log
cat logs/monitor.log
```

---

## Despliegue automático en Railway (gratis)

1. Sube el proyecto a GitHub (repositorio privado)
2. Entra a [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. En Variables de entorno agrega: `RESEND_API_KEY=re_xxxxx`
4. En Settings → Cron Jobs agrega: `0 7 * * *` (corre cada día a las 7am)

¡Listo! El sistema corre solo todos los días.

---

## Estructura del proyecto

```
guatecompras-alertas/
├── monitor.py          ← Script principal
├── test_conexion.py    ← Verificar que funciona
├── requirements.txt    ← Dependencias Python
├── data/
│   └── alertas.db      ← Base de datos (se crea automático)
└── logs/
    └── monitor.log     ← Log de ejecuciones
```

---

## Costos mensuales

| Servicio     | Plan       | Costo    |
|-------------|------------|----------|
| Railway     | Hobby free | $0       |
| Resend      | Free tier  | $0       |
| Dominio     | Opcional   | ~$12/año |
| **Total**   |            | **$0–$1/mes** |

Con 5 clientes a Q1,200/mes = **~Q6,000/mes** de ingreso.

---

## Agregar alertas por WhatsApp (opcional, clientes premium)

Reemplaza `enviar_email_resend()` con una llamada a Z-API:

```python
import requests

def enviar_whatsapp(numero: str, mensaje: str):
    # Número formato: 502XXXXXXXX (Guatemala)
    requests.post(
        f"https://api.z-api.io/instances/TU_INSTANCIA/token/TU_TOKEN/send-text",
        json={"phone": numero, "message": mensaje}
    )
```

Costo Z-API: ~$15/mes para uso comercial.
