from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_URL = os.getenv("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1")
JAN_START = date(2026, 1, 1)
JAN_END = date(2026, 1, 31)
app = FastAPI(title="WindBrief API", version="1.0.0")

_cache: dict[str, Any] = {"actuals": None, "forecasts": None, "loaded_at": None}
_load_lock = asyncio.Lock()


async def fetch_json(client: httpx.AsyncClient, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    response = await client.get(f"{BASE_URL}/{path}", params={**params, "format": "json"})
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        data = data.get("data", [])
    if not isinstance(data, list):
        raise ValueError(f"Unexpected Elexon payload for {path}")
    return data


async def load_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if _cache["actuals"] is not None and _cache["forecasts"] is not None:
        return _cache["actuals"], _cache["forecasts"]
    async with _load_lock:
        if _cache["actuals"] is not None and _cache["forecasts"] is not None:
            return _cache["actuals"], _cache["forecasts"]
        timeout = httpx.Timeout(60.0, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Elexon FUELHH accepts settlementDateFrom/To. Fetch by month, then retain WIND.
            actuals_task = fetch_json(client, "datasets/FUELHH/stream", {
                "settlementDateFrom": JAN_START.isoformat(), "settlementDateTo": JAN_END.isoformat()
            })
            # WINDFOR records are versioned by publication time. Daily chunks include each
            # available publication so the selected as-of snapshot can be reconstructed.
            forecast_tasks = []
            day = datetime(2025, 12, 31, tzinfo=timezone.utc)
            last = datetime(2026, 2, 1, tzinfo=timezone.utc)
            while day < last:
                nxt = day + timedelta(days=1)
                forecast_tasks.append(fetch_json(client, "datasets/WINDFOR/stream", {
                    "publishDateTimeFrom": day.isoformat().replace("+00:00", "Z"),
                    "publishDateTimeTo": nxt.isoformat().replace("+00:00", "Z"),
                }))
                day = nxt
            try:
                actual_rows, forecast_chunks = await asyncio.gather(
                    actuals_task, asyncio.gather(*forecast_tasks, return_exceptions=True)
                )
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"Elexon data request failed: {exc}") from exc
        failures = [x for x in forecast_chunks if isinstance(x, Exception)]
        if failures:
            raise HTTPException(status_code=502, detail=f"Elexon forecast feed failed: {failures[0]}")
        actuals = [r for r in actual_rows if r.get("fuelType") == "WIND" and r.get("startTime")]
        forecasts = [r for chunk in forecast_chunks for r in chunk if r.get("startTime") and r.get("publishTime")]
        _cache.update(actuals=actuals, forecasts=forecasts, loaded_at=datetime.now(timezone.utc).isoformat())
        return actuals, forecasts


def metrics(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    matched = [r for r in rows if isinstance(r.get("actual"), (int, float)) and isinstance(r.get("forecast"), (int, float))]
    if not matched:
        return {"intervals": 0, "mae": None, "rmse": None, "bias": None, "wape": None}
    errors = [float(r["forecast"]) - float(r["actual"]) for r in matched]
    actual_sum = sum(abs(float(r["actual"])) for r in matched)
    return {
        "intervals": len(matched),
        "mae": sum(abs(e) for e in errors) / len(errors),
        "rmse": (sum(e * e for e in errors) / len(errors)) ** 0.5,
        "bias": sum(errors) / len(errors),
        "wape": (sum(abs(e) for e in errors) / actual_sum * 100) if actual_sum else None,
    }


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "data_loaded": _cache["actuals"] is not None, "loaded_at": _cache["loaded_at"]}


@app.get("/api/analysis")
async def analysis(
    day: date = Query(default=date(2026, 1, 15)),
    decision_time: str = Query(default="10:00"),
) -> dict[str, Any]:
    if day < JAN_START or day > JAN_END:
        raise HTTPException(status_code=400, detail="Choose a delivery date in January 2026.")
    try:
        hour, minute = (int(part) for part in decision_time.split(":"))
        if not (0 <= hour <= 23 and minute in (0, 30)):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=400, detail="Decision time must be HH:00 or HH:30.")
    actuals, forecasts = await load_data()
    cutoff = datetime.combine(day - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).replace(hour=hour, minute=minute)
    actual_by_time: dict[str, float] = {}
    for row in actuals:
        if str(row.get("settlementDate")) == day.isoformat():
            try:
                actual_by_time[row["startTime"]] = float(row["generation"])
            except (KeyError, TypeError, ValueError):
                continue
    # Reduce to latest publication known at the cutoff for each delivery interval.
    selected: dict[str, dict[str, Any]] = {}
    for row in forecasts:
        try:
            published = datetime.fromisoformat(row["publishTime"].replace("Z", "+00:00"))
            target = datetime.fromisoformat(row["startTime"].replace("Z", "+00:00"))
            generation = float(row["generation"])
        except (KeyError, TypeError, ValueError):
            continue
        if target.date() != day or published > cutoff:
            continue
        previous = selected.get(row["startTime"])
        if previous is None or row["publishTime"] > previous["publishTime"]:
            selected[row["startTime"]] = {"forecast": generation, "publishTime": row["publishTime"]}
    # WINDFOR is hourly while FUELHH is half-hourly. Carry each hourly value
    # into the following half-hour slot when Elexon has no explicit forecast there.
    for timestamp, value in list(selected.items()):
        target = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if target.minute == 0:
            half_hour = (target + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
            if half_hour not in selected:
                selected[half_hour] = value
    rows = []
    for timestamp in sorted(set(actual_by_time) | set(selected)):
        pick = selected.get(timestamp, {})
        rows.append({
            "startTime": timestamp,
            "actual": actual_by_time.get(timestamp),
            "forecast": pick.get("forecast"),
            "publishTime": pick.get("publishTime"),
            "error": (pick["forecast"] - actual_by_time[timestamp]) if "forecast" in pick and timestamp in actual_by_time else None,
        })
    publication_times = sorted({r["publishTime"] for r in rows if r["publishTime"]})
    return {
        "day": day.isoformat(), "decisionCutoff": cutoff.isoformat(), "rows": rows,
        "metrics": metrics(rows), "latestPublishTime": publication_times[-1] if publication_times else None,
        "forecastRuns": len(publication_times), "dataLoadedAt": _cache["loaded_at"],
        "source": "Elexon BMRS Insights API",
    }


frontend = Path(os.getenv("FRONTEND_DIST", Path(__file__).parent.parent / "frontend" / "dist"))
if frontend.exists():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        root = frontend.resolve()
        target = (frontend / full_path).resolve()
        if not target.is_relative_to(root):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(target if target.is_file() else frontend / "index.html")
