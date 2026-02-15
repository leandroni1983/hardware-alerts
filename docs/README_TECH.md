# Hardware Alerts — Technical README

**Propósito:** Sistema de monitorización de precios de hardware (CPU/GPU/SSD/RAM) que detecta mejores ofertas y notifica vía Telegram.

**Componentes principales**
- `scrapers/` : implementaciones por tienda (Playwright/requests).
- `runner.py` / `services.scraper_runner` : orquesta scrapers, normaliza `product_key`, llama `storage.scraper_db.insert_items`.
- `storage/scraper_db.py` : SQLite, tablas principales: `scraped_items`, `scraped_price_history`, `scraped_price_history_key`, `scraped_best_offers`, `notified_offers`.
- `worker/alerter.py` : evalúa thresholds, muestras y flags (`AI_ENABLED`, `SEND_ONLY_REAL`), envía ofertas.
- `notifier/telegram_bot.py` : formatea mensajes y llama Bot API; lee `config/telegram.env`.
- `scripts/telegram_async_bot.py` : listener de comandos (p.ej. `/best`).
- `main.py` : FastAPI entrypoint (exponer endpoints operativos).

**Archivos añadidos**
- [docs/ARCHITECTURE.mmd](docs/ARCHITECTURE.mmd) — diagrama Mermaid del flujo.
- [docs/README_TECH.md](docs/README_TECH.md) — este fichero.

**Ejecución (Docker)**
```bash
docker compose up -d --build
```
- Servicios: `app` (FastAPI :8001), `runner` (one-off), `alerter` (worker), `telegram-listener`.
- DB persistente en `./data` (configurable con `SCRAPER_DB_PATH`).

**Ejecución (local, debugging)**
```bash
pip install -r requirements.txt
python -c "from storage.scraper_db import init_db; init_db()"
uvicorn main:app --host 0.0.0.0 --port 8001
python runner.py   # run scrapers + processing
python worker/alerter.py  # start alerter
```

**Variables de entorno / configuración**
- `SCRAPER_DB_PATH` — ruta del fichero SQLite (override).
- `TELEGRAM_TOKEN_FILE` — ruta a `config/telegram.env` (contiene `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`).
- Worker flags en `docker-compose.yml`: `ALERT_INTERVAL_MIN`, `NOTIFY_SEND`, `AI_ENABLED`, `SEND_ONLY_REAL`, `NOTIFY_LIMIT_KEYS`, `NOTIFY_MIN_SAMPLES`, `NOTIFY_THRESHOLD_PCT`.

**Dónde ver el diagrama**
- Abrir [docs/ARCHITECTURE.mmd](docs/ARCHITECTURE.mmd) en VSCode con extensión Mermaid o pegar en https://mermaid.live/ para renderizado.

**Próximos pasos (breve)**
- Contenerizar Playwright (navegadores) en `Dockerfile`.
- Considerar migración a Postgres para concurrencia y backups.
- Mover secrets a Docker secrets / Vault.
