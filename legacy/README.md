# `legacy/` — SQLite + Sense HAT display

This folder is **not** dead code. The main Flask app (`api.create_app`) still imports from here when optional features are enabled:

| Module | Used for |
|--------|----------|
| `database.py` | Optional local SQLite mirror when `USE_SQLITE_CACHE=1` |
| `display_service.py` | Sense HAT LED matrix (startup / warnings / errors) when hardware is available |
| `app.py` | Alternate entrypoint: `python -m legacy.app` → same `create_app()` as `run.py` |

Authentication lives under `api/auth.py` (not in this folder).
