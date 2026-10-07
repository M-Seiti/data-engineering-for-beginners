import json
import logging

from datetime import date
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("transform")

# Repository root: transform.py -> 02-raw-to-staging -> code -> root
DATA_DIR = Path(__file__).resolve().parents[2] / "data"

FIXED_COLUMNS = ["date", "latitude", "longitude", "collected_at"]


# Reads the raw JSON saved by lesson 01
def read_raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# Turns the parallel lists into one row per day, plus context columns
def to_dataframe(raw: dict) -> pd.DataFrame:
    body = raw["body"]

    df = pd.DataFrame(body["daily"])
    df = df.rename(columns={"time": "date"})

    df["latitude"] = body["latitude"]
    df["longitude"] = body["longitude"]
    df["collected_at"] = raw["meta"]["collected_at"]
    return df


# Converts every column to its declared type
def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(FIXED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], format="%Y-%m-%d")
    out["collected_at"] = pd.to_datetime(out["collected_at"], utc=True)

    numeric = [col for col in out.columns if col not in ("date", "collected_at")]
    for col in numeric:
        # errors="raise": an invalid value stops the program instead of becoming empty
        out[col] = pd.to_numeric(out[col], errors="raise").astype("float64")

    variables = [col for col in out.columns if col not in FIXED_COLUMNS]
    return out[FIXED_COLUMNS + variables]


# Checks the content; any problem stops the pipeline
def validate(df: pd.DataFrame, start: date, end: date) -> None:
    errors = []

    if df["date"].duplicated().any():
        errors.append("repeated dates")

    expected_days = pd.date_range(start, end, freq="D")
    missing_days = expected_days.difference(df["date"])
    if len(missing_days) > 0:
        errors.append(f"missing days: {[d.date().isoformat() for d in missing_days]}")

    if "precipitation_sum" in df.columns and (df["precipitation_sum"] < 0).any():
        errors.append("negative rain")

    if errors:
        raise ValueError("Validation failed: " + "; ".join(errors))

    nulls = int(df.drop(columns=FIXED_COLUMNS).isna().sum().sum())
    if nulls:
        log.warning("%s empty values (the API had no data for them)", nulls)


# Saves as Parquet, with the same atomic trick as raw_save
def save_staging(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    log.info("staging saved to %s (%s rows)", path, len(df))


if __name__ == "__main__":
    start, end = date(2024, 3, 1), date(2024, 3, 7)

    raw_path = DATA_DIR / "raw" / "open_meteo" / f"{start}_{end}.json"
    staging_path = DATA_DIR / "staging" / "open_meteo" / f"{start}_{end}.parquet"

    raw = read_raw(raw_path)
    df = to_dataframe(raw)
    df = enforce_schema(df)
    validate(df, start, end)
    save_staging(df, staging_path)

    print(df)
    print(df.dtypes)
