# Repository Guidelines

## Project Structure & Module Organization
`app.py` is the FastAPI entrypoint and contains the HTTP routes, scheduler startup, and health checks. Keep reusable logic out of route handlers when possible. `auth.py` handles JWT auth and DB session dependencies, `models.py` defines SQLAlchemy models, `services/` contains crawling, database, and RAG logic, and `core/` holds shared helpers. Frontend assets live in `templates/` (`index.html`, `main.js`). Deployment and ops material lives in `docs/`, `Dockerfile`, `fly.toml`, and `docker-compose.production.yml`.

## Build, Test, and Development Commands
Create a local environment with `python -m venv venv` and `source venv/bin/activate`, then install dependencies with `pip install -r requirements.txt`. Run the app locally with `python app.py`; this starts Uvicorn in reload mode on `http://localhost:8000`. For container validation, use `docker compose -f docker-compose.production.yml up --build`. Verify the service with `curl http://localhost:8000/health`, and use `/health/db` or `/health/vectorstore` when changes touch persistence or RAG.

## Coding Style & Naming Conventions
Follow the existing Python style: 4-space indentation, `snake_case` for modules/functions/variables, `PascalCase` for model classes, and explicit imports grouped at the top of each file. Preserve type hints where they already exist and add them for new service helpers. Keep FastAPI endpoints thin and move scraping, DB, or AI logic into `services/`. In `templates/main.js`, use descriptive `camelCase` names and avoid introducing a framework unless the repo is intentionally being restructured.

## Testing Guidelines
There is no committed automated test suite yet. For every change, document manual verification steps and exercise the affected endpoint or UI flow locally. If you add automated coverage, place tests under `tests/` and use `pytest` with filenames like `test_auth.py` or `test_scraper.py`. Prioritize parser edge cases, auth flows, and database write paths.

## Commit & Pull Request Guidelines
Recent history uses short, imperative commits with prefixes such as `feat:`, `fix:`, and `ci:`. Keep that pattern and scope each commit to one logical change. PRs should include a concise summary, deployment or env-var impact, linked issue if available, and screenshots when `templates/` output changes.

## Security & Configuration Tips
Never commit live secrets in `.env`. Use `.env.production.example` as the template for required settings such as `SECRET_KEY`, `ADMIN_SECRET`, OAuth keys, and `BASE_URL`. Treat `/data` backups and ChromaDB contents as runtime state, not source files.
