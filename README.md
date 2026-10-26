# WindBrief

WindBrief is a day-ahead wind forecast review workspace for the UK power market. It pairs Elexon national wind forecasts with actual generation for January 2026 and lets an analyst inspect the latest forecast available at a chosen decision cutoff.

## Run locally

```bash
docker compose up --build
```

Open http://localhost:8000. The API health check is at `/api/health`.

For development without Docker, start the backend and frontend in separate terminals:

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

```bash
cd frontend && pnpm install --frozen-lockfile && pnpm dev
```

The Vite development server runs at http://localhost:5173 and proxies `/api` requests to port 8000.

Data is fetched from Elexon's public [BMRS Insights API](https://developer.data.elexon.co.uk/) by the backend and cached in memory for the process lifetime. The app uses only [FUELHH](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream) (WIND) and [WINDFOR](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream). No API key is required. AI assistance was used to develop this application.

## Repository map

- `backend/` — FastAPI service, Elexon ingestion, forecast selection and evaluation metrics.
- `frontend/` — React + TypeScript dashboard.
- `docker-compose.yml` — local full-stack orchestration.
- `Dockerfile` — multi-stage container serving the frontend and API behind one origin.

## Analysis semantics

For each half-hour target interval, WindBrief selects the most recently published WINDFOR value whose `publishTime` is no later than the selected cutoff. Actual wind output is sourced from FUELHH records where `fuelType` is `WIND`. Forecast and actual are joined on `startTime`. Error is forecast minus actual; MAE, RMSE, mean bias, and WAPE are calculated only on matched intervals. Forecasts are hourly while actuals are half-hourly, so the forecast series is carried onto each matching half-hour interval without interpolation.

At a 10:00 UK cutoff for each January 2026 delivery day, the 1,488 matched half-hour intervals have an overall MAE of 2,126 MW, RMSE of 2,621 MW, mean bias of +1,840 MW, and WAPE of 18.36%. This is a historical evaluation, not a trading recommendation. The app does not estimate customer demand or procurement volumes because the challenge limits inputs to wind forecast and wind actual data.

## Deployment

The container listens on port 8000 and serves both the API and built frontend. `vercel.toml` also defines the React frontend and FastAPI backend as two services in one Vercel project. Import the repository in Vercel and deploy from the repository root; Vercel routes `/api/*` to FastAPI and other paths to the frontend. Vercel's current Python and full-stack service setup is documented at https://vercel.com/changelog/python-on-vercel-is-now-generally-available.

Public deployment URL: pending Vercel deployment. Public anonymous GitHub repository: https://github.com/uniyal802/w6r9k2p1.
