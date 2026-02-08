# hardware-alerts

Scrape precios de hardware en Argentina, detectar ofertas y notificar por Telegram.

Requisitos locales:
- Python 3.11
- Playwright (instalar y ejecutar `playwright install`)
- Ollama corriendo localmente en el puerto 11434 con el modelo `qwen2.5:3b-instruct`

Instalación rápida (Windows / PowerShell):

```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
playwright install
```

Configurar Telegram en `config/telegram.env`:

```
TELEGRAM_TOKEN=123456:ABCDEF
TELEGRAM_CHAT_ID=987654321
```

Ejecutar localmente:

```powershell
python main.py
```

Docker:
- Proporciono un `docker-compose.yml` orientativo. Para producción cree un `Dockerfile`
  que instale Playwright browsers y Ollama (si es necesario) o ejecute Ollama por separado.

Notas:
- Ollama se usa solo para clasificación (REAL / NORMAL / HUMO). La lógica de detección
  dura (15% por debajo de promedio 30d) se ejecuta en Python.
- Las tablas SQLite se inicializan automáticamente en `storage/prices.db`.

## Cron runner y SQLite (scraper)
Este flujo es independiente de FastAPI y se ejecuta desde `runner.py`.

### Estructura de archivos (mínima)
```
hardware-alerts/
├─ runner.py
├─ services/
│  └─ scraper_runner.py
└─ storage/
   └─ scraper_db.py
```

### Base de datos
- Ruta absoluta: `/opt/scraper/data.db`
- Se crea automáticamente si no existe.

### Creación de tablas (SQL)
```
CREATE TABLE IF NOT EXISTS scraped_items (
    id INTEGER PRIMARY KEY,
    shop_id TEXT NOT NULL,
    shop_name TEXT NOT NULL,
    category TEXT,
    product_name TEXT NOT NULL,
    price INTEGER,
    stock INTEGER,
    product_url TEXT NOT NULL UNIQUE,
    scraped_at TEXT NOT NULL,
    summary TEXT,
    processed INTEGER NOT NULL DEFAULT 0,
    processed_at TEXT
);
```

### Inserción (Python)
```
from storage.scraper_db import insert_items

inserted, skipped = insert_items(items)
```

### Consulta de no procesados (Python)
```
from storage.scraper_db import get_unprocessed

rows = get_unprocessed(limit=100)
```

### Marcado como procesado (Python)
```
from storage.scraper_db import mark_processed

mark_processed(item_id=1, summary="Resumen corto...")
```

### Ejecución por cron (ejemplo)
Cada 5 minutos:
```
*/5 * * * * /usr/bin/python3 /opt/scraper/hardware-alerts/runner.py >> /opt/scraper/runner.log 2>&1
```
