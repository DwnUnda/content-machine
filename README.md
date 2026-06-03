# Home Dry Lab Content Machine

Local-first foundation for producing research-backed WordPress blog draft content for Home Dry Lab.

## Apps
- `apps/api`: FastAPI backend, SQLite, SQLAlchemy, Alembic
- `apps/web`: Next.js operator UI

## Local Development

### Environment
Create and fill the local `.env` file at the repo root before running live integrations.

Required for live DataForSEO verification:
```bash
DATAFORSEO_LOGIN=your-login
DATAFORSEO_PASSWORD=your-password
```

### API
```bash
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Web
```bash
cd apps/web
npm install
npm run dev
```

## Default URLs
- API: `http://localhost:8000`
- Web: `http://localhost:3000`

## Live DataForSEO Check
After filling `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD` in the repo-root `.env`:

1. Start the API and web app.
2. Open the Settings page and confirm DataForSEO shows as configured.
3. Create an article job with the keyword `best dehumidifier for mould australia`.
4. Run `SERP Research`.
5. Run `Keyword Research`.
6. Confirm stored results appear in the article detail tabs.
