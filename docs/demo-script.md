# WindBrief demo script

Use a screen recording with microphone narration. Keep the complete video under 10 minutes and publish it as an unlisted YouTube video.

## Part 1 — Customer walkthrough (about 4 minutes)

**0:00–0:30 — Set the context**

“This pilot helps the day-ahead desk review national wind forecasts using only the Elexon data in scope. The aim is to make the forecast available at the decision cutoff visible and to quantify how it compared with actual generation.”

**0:30–1:15 — Select a delivery day and cutoff**

Show delivery date and cutoff controls. Explain that a chosen cutoff means forecasts published later are excluded. At 10:00 UK time on January 14 for January 15 delivery, the latest eligible forecast publication is 09:30.

**1:15–2:15 — Read the chart and snapshot**

Show the forecast and actual curves. Explain that actual FUELHH data is half-hourly, while WINDFOR is hourly; the hourly forecast is carried forward to the second half-hour, without interpolation. Hover over a point and compare MW values.

**2:15–3:15 — Explain forecast quality**

Show MAE, RMSE, bias, and WAPE. For January 15 at the selected cutoff, the day had 48 matched intervals, MAE 1,110 MW, RMSE 1,229 MW, positive mean bias 1,110 MW, and WAPE 10.5%. Positive bias means the forecast was above actual output on average.

**3:15–4:00 — Review intervals and export**

Open Intervals, point out the forecast publication timestamp and signed error, then export CSV. Close by stating this is a forecast review aid; wind-only data is not enough to calculate total procurement need or recommend a trade.

## Part 2 — Technical review (about 4 minutes)

**4:00–4:45 — Architecture**

Explain React + TypeScript + Vite frontend, FastAPI/Python backend, and Docker packaging. The frontend requests `/api/analysis`; the backend reads Elexon and returns aligned rows, metadata, and metrics.

**4:45–5:45 — Data and as-of logic**

Show `backend/main.py`. FUELHH is filtered to `fuelType = WIND` and January settlement dates. WINDFOR publication history is fetched by `publishTime` day chunks from December 31 through January 31, so January delivery days can use forecasts issued on the preceding day. For every target period, the backend chooses the latest publication no later than the selected cutoff.

**5:45–6:45 — Alignment and metrics**

Explain that FUELHH records are half-hourly and WINDFOR records are hourly. Each forecast is applied to the matching hour's two half-hour outturn intervals. Error is forecast minus actual. MAE is average absolute error; RMSE penalizes larger misses; bias retains direction; WAPE scales absolute errors by total absolute actual generation.

**6:45–7:30 — Frontend and interaction**

Show `frontend/src/App.tsx`: date and cutoff filters, overview chart, interval table, and CSV export. The API response is reused for both views; no client-side Elexon credentials are needed.

**7:30–8:00 — Run and constraints**

Show `docker-compose.yml` and README. Run `docker compose up --build`. Note that the process caches fetched data in memory and that Elexon requests are public and keyless. Mention that January 2026 at 10:00 cutoff produced 1,488 intervals with MAE 2,126 MW, RMSE 2,621 MW, mean bias +1,840 MW, and WAPE 18.36%.

**8:00–8:15 — Handoff**

“This pilot stays within the required two datasets. It does not use load, prices, or other sources, so it surfaces wind uncertainty rather than calculating the utility’s full residual demand.”
