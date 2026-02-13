# Propuesta de limpieza (Cleanup Proposal)

Este archivo propone qué archivos/carpetas archivar o eliminar con bajo riesgo, por qué y cómo hacerlo de forma segura.

## Objetivo
- Reducir ruido en el repo moviendo scripts temporales/depuración a `archive/`.
- Mantener el historial con `git mv` y poder recuperar si es necesario.

## Archivar (recomendado)
Mover estos archivos a `archive/` si no los usás activamente:

- `tmp_test_cpu.py` — pruebas puntuales locales.
- `tmp_test_amd.py` — pruebas puntuales locales.
- `tmp_db/` — snapshots/DB temporales (hacer backup si hay datos útiles).
- `scripts/debug_gezatek.py` — debugging específico de tienda.
- `scripts/debug_check.py` — utilidad de depuración local.

## Archivar / revisar (posible archivo)
- `scripts/inspect_offer.py` — inspección manual; archivar si no se usa.
- `scripts/inspect_scraper_db.py` — similar, revisar si se usa ocasionalmente.
- `scripts/fix_gezatek_prices.py` — correcciones históricas; archivar si no aplicas más.

## Mantener (NO tocar)
- `scrapers/`, `normalizers/`, `storage/`, `notifier/`, `worker/`, `scripts/telegram_listener.py`, `scripts/backfill_product_keys.py`, `docker-compose.yml`, `Dockerfile`, `config/`, `data/`.

## Limpieza de artefactos Python
Eliminar caches y archivos compilados (si querés limpieza rápida):

```sh
find . -name "__pycache__" -type d -exec rm -rf {} +
find . -name "*.pyc" -delete
```

## Comandos sugeridos para archivar (conservar historial)

```sh
mkdir -p archive
git mv tmp_test_cpu.py tmp_test_amd.py archive/ || mv tmp_test_cpu.py tmp_test_amd.py archive/
git mv tmp_db archive/ || mv tmp_db archive/
git mv scripts/debug_*.py archive/ || mv scripts/debug_*.py archive/
git mv scripts/inspect_*.py archive/ || mv scripts/inspect_*.py archive/
```

Después de mover:

```sh
git add -A
git commit -m "chore: archive temporary and debug scripts"
```

## Backups / comprobaciones antes de borrar
1. Ejecutar tests y scripts de validación (`python scripts/test_normalizers.py`, `python -m py_compile ...`).
2. Hacer backup de `data/` si contiene DB productiva.
3. Ejecutar `scripts/backfill_product_keys.py --dry-run` si vas a cambiar la normalización.

## Checklist (marcar antes de borrar)
- [ ] Crear rama `chore/cleanup` y push.
- [ ] Mover archivos a `archive/` con `git mv`.
- [ ] Ejecutar pruebas y backfill dry-run.
- [ ] Confirmar en entorno de staging/containter que scrapers+alerter funcionan.
- [ ] Merge y luego eliminar archivo archivado de la rama principal tras 1-2 semanas.

---

Si querés, aplico los `git mv` ahora y creo la rama `chore/cleanup` (te dejo aprobar antes de commitear). 
