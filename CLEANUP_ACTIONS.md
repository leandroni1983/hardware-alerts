# Cleanup actions performed

Resumen de operaciones ejecutadas automáticamente para dejar el repo más prolijo:

- Creada rama: `chore/cleanup`.
- Archivados los helpers: `scripts/archive_cleanup.ps1`, `scripts/move_selected_untracked_to_archive.ps1` → `archive/scripts/`.
- Eliminados artefactos Python: todas las carpetas `__pycache__/` y archivos `*.pyc` recursivamente.
- Añadido `scripts/clean_pycache.ps1` como utilidad para limpiar caches (si se desea, puede moverse a `archive/`).
- Commits generados: `chore: archive helper cleanup scripts`, `chore: remove __pycache__ and .pyc artifacts`.

Notas:
- No se movieron archivos de código fuente esenciales; solo helpers y artefactos.
- El script original `CLEANUP_PROPOSAL.md` sigue presente con recomendaciones.
