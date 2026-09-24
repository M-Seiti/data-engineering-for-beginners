import requests
import os
import time
import logging
import json

from pathlib import Path
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from datetime import datetime, timezone, date

TIMEOUT_S = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("api.client")


def session_maker() -> requests.Session:
    session = requests.Session()

    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))

    session.headers.update({
        "User-Agent": "estudo-engenharia-dados/0.1 (youremail@example.com)",
        "Accept": "application/json",
    })

    token = os.environ.get("API_TOKEN")
    if token:
        session.headers["chave-api-dados"] = token

    return session


def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
    start = time.perf_counter()
    resp = session.get(url, params=params, timeout=TIMEOUT_S)
    duration = round(time.perf_counter() - start, 2)

    log.info("GET %s status=%s duration=%ss", resp.url, resp.status_code, duration)

    resp.raise_for_status()

    if "json" not in resp.headers.get("Content-Type", ""):
        raise ValueError(f"Response is not JSON: {resp.headers.get('Content-Type')}")

    return {
        "meta": {
            "url": resp.url,
            "status": resp.status_code,
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duration_s": duration,
        },
        "body": resp.json(),
    }


def raw_save(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    log.info("raw saved to %s", path)


def open_meteo_rain(session: requests.Session, lat: float, lon: float, start: date, end: date) -> dict:
    return get_json(
        session,
        "https://archive-api.open-meteo.com/v1/archive",
        {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "precipitation_sum",
            "timezone": "America/Sao_Paulo",
        },
    )


if __name__ == "__main__":
    session = session_maker()

    start, end = date(2024, 3, 1), date(2024, 3, 7)
    weather = open_meteo_rain(session, -16.72, -43.86, start, end)
    raw_save(weather, Path(f"data/raw/open_meteo/{start}_{end}.json"))

    daily = weather["body"]["daily"]
    for day, rain in zip(daily["time"], daily["precipitation_sum"]):
        print(f"{day}: {rain} mm")
