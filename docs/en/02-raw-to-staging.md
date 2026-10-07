# Lesson 02 — From Raw Data to a Clean Table

[🏠 Index](README.md) · [⬅️ Lesson 01](01-open-meteo-client.md) · [🇧🇷 Português](../pt/02-raw-to-staging.md) · [💻 Code](../../code/02-raw-to-staging/)

---

## What you will learn

- [ ] How to read the raw JSON saved in lesson 01
- [ ] How to turn parallel lists into a table with one row per day
- [ ] How to declare and convert each column's type explicitly
- [ ] How to add context columns (location and collection time)
- [ ] How to validate the content and stop the pipeline when something is wrong
- [ ] How to save the result as Parquet, and why Parquet instead of CSV

## Before you start

**Run lesson 01 first.** This lesson doesn't call the API. It reads the file that lesson 01 saved in `data/raw/open_meteo/`. That is the whole point of the raw layer: the transformation can run, break and run again without spending a single request.

Install the new libraries:

```bash
pip install pandas pyarrow
```

- **`pandas`** works with tables (called *DataFrames*).
- **`pyarrow`** is what pandas uses behind the scenes to write Parquet files. You never import it, but without it `to_parquet` fails.

### Look at the data first

The most common reason to get lost in a transformation is not knowing the shape of what you are transforming. Open the JSON from lesson 01. It looks like this:

```json
{
  "meta": { "collected_at": "2026-09-24T13:00:00+00:00", "...": "..." },
  "body": {
    "latitude": -16.75,
    "longitude": -43.875,
    "daily": {
      "time":              ["2024-03-01", "2024-03-02", "2024-03-03"],
      "precipitation_sum": [0.0,          3.2,          null]
    }
  }
}
```

Two things to notice:

- Inside `daily` there are **two lists of the same size**, and the position connects them. The first date in `time` goes with the first value in `precipitation_sum`, and so on. These are called **parallel lists**. Our job in this lesson is to turn them into a table with one row per day.
- We asked for latitude `-16.72`, but the API answered `-16.75`. Open-Meteo works with a grid of points and returns the closest one. That's why we keep the coordinates **from the response**, not the ones we asked for.

---

## Part 1 — Libraries and settings

```python
import json
import logging

from datetime import date
from pathlib import Path

import pandas as pd
```

You already know `json`, `logging`, `date` and `Path` from lesson 01. The new one is **`pandas`**, imported as `pd`. The `as pd` is just a shorter name; it's a convention used by almost everyone.

> 💡 Python's standard library comes first, and installed libraries (`pandas`) come last, separated by a blank line. This order comes from PEP 8 and makes it easy to see what needs to be installed.

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("transform")
```

The same logging setup as lesson 01, with a different logger name, so we know which script wrote each message.

```python
# Repository root: transform.py -> 02-raw-to-staging -> code -> root
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
```

The same `data/` folder at the repository root that lesson 01 uses. `.parents[2]` goes up three levels: from the file to its folder, then to `code/`, then to the root. Because both lessons point to the same place, lesson 02 finds the file that lesson 01 saved.

```python
FIXED_COLUMNS = ["date", "latitude", "longitude", "collected_at"]
```

The columns that **always** exist in our table. Every other column will be a weather variable, like `precipitation_sum`. Keeping this list in one place lets the code work with any number of weather variables without changes.

---

## Part 2 — Reading the raw file

```python
# Reads the raw JSON saved by lesson 01
def read_raw(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
```

This is `raw_save` in reverse:

- `path.read_text(encoding="utf-8")` reads the whole file as text.
- `json.loads(...)` turns that text back into a Python dictionary.

> 💡 `json.dumps` (with an **s**) turns a dictionary into text; `json.loads` turns text into a dictionary. The **s** stands for *string*.

---

## Part 3 — From parallel lists to a table

```python
# Turns the parallel lists into one row per day, plus context columns
def to_dataframe(raw: dict) -> pd.DataFrame:
    body = raw["body"]

    df = pd.DataFrame(body["daily"])
    df = df.rename(columns={"time": "date"})
```

- **`body = raw["body"]`** keeps the API's answer in a short variable, so we don't repeat `raw["body"]` everywhere.
- **`pd.DataFrame(body["daily"])`** does almost all the work. When you give pandas a **dictionary of lists**, **each key becomes a column** and each position in the lists becomes a row:

  ```
           time  precipitation_sum
  0  2024-03-01                0.0
  1  2024-03-02                3.2
  2  2024-03-03                NaN
  ```

  The `null` from the JSON became `NaN` (*Not a Number*), which is how pandas represents an empty number.
- **`df.rename(columns={"time": "date"})`** changes the column name from `time` to `date`, which describes the content better. `rename` returns a **new** table, so we store it back in `df`.

> 💡 If you request more variables in lesson 01 (for example `"precipitation_sum,temperature_2m_max"`), `daily` will have more lists, and this same line will create more columns. Nothing in the code needs to change.

### Context columns

```python
    df["latitude"] = body["latitude"]
    df["longitude"] = body["longitude"]
    df["collected_at"] = raw["meta"]["collected_at"]
    return df
```

When you assign a **single value** to a column, pandas repeats it in every row. In a 7-row table it looks redundant, but when you later combine data from many cities and many collections into one table, these columns tell you where each row came from.

Note that `collected_at` comes from `meta`, the part that lesson 01 wrote about the request itself.

---

## Part 4 — Declaring the schema

At this point, the `date` column is still **text**, not a date. pandas doesn't guess that for you, and that's a good thing: a wrong guess is worse than no guess.

### Checking that the columns exist

```python
# Converts every column to its declared type
def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(FIXED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
```

- `set(...)` turns a list into a **set**: a collection without repeated items and without order.
- Subtracting two sets (`-`) gives the items that are in the first one and **not** in the second. So `missing` contains the fixed columns that didn't come in the data.
- An empty set counts as `False` in an `if`, so the error is only raised when something is missing.

If you think in C, the same check with loops would be:

```python
missing = []
for col in FIXED_COLUMNS:
    if col not in df.columns:
        missing.append(col)
```

Both versions do the same thing. The set version is shorter and is what you will see in most Python code.

### Converting the dates

```python
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], format="%Y-%m-%d")
    out["collected_at"] = pd.to_datetime(out["collected_at"], utc=True)
```

- **`df.copy()`** creates an independent copy. We change `out`, and the original `df` stays untouched. Changing data that someone else passed to your function is a common source of hard-to-find bugs.
- **`pd.to_datetime(..., format="%Y-%m-%d")`** converts text into dates. The `format` says exactly how the text is written: four-digit year, month, day. If a date arrives in another format, the conversion **fails** instead of guessing (is `03/04` March 4th or April 3rd?).
- **`utc=True`** keeps `collected_at` in UTC, the same timezone lesson 01 used to write it.

### Converting the numbers

```python
    numeric = [col for col in out.columns if col not in ("date", "collected_at")]
```

This is a **list comprehension**: a compact way to build a list. Read it as "a list with each `col` from `out.columns`, keeping only those that are not `date` or `collected_at`". The loop version is:

```python
numeric = []
for col in out.columns:
    if col not in ("date", "collected_at"):
        numeric.append(col)
```

The result is every column that should be a number: `latitude`, `longitude` and all weather variables.

```python
    for col in numeric:
        # errors="raise": an invalid value stops the program instead of becoming empty
        out[col] = pd.to_numeric(out[col], errors="raise").astype("float64")
```

- **`pd.to_numeric(..., errors="raise")`** converts the column to numbers. If any value can't be converted (for example the text `"lots"`), the program **stops** with an error. The alternative, `errors="coerce"`, would silently turn that value into `NaN`, and you would never know the data arrived broken.
- **`.astype("float64")`** makes sure every numeric column has the same type: a decimal number with 64 bits of precision, the equivalent of `double` in C.

### Ordering the columns

```python
    variables = [col for col in out.columns if col not in FIXED_COLUMNS]
    return out[FIXED_COLUMNS + variables]
```

`variables` is every column that is not fixed: the weather variables. `FIXED_COLUMNS + variables` joins the two lists, and `out[...]` with a list of names returns the table **with the columns in that order**. Fixed columns first, variables after: every staging file will have the same layout.

---

## Part 5 — Validating the content

The schema checks the **shape** of the data: columns and types. Validation checks if the **content** makes sense.

```python
# Checks the content; any problem stops the pipeline
def validate(df: pd.DataFrame, start: date, end: date) -> None:
    errors = []
```

We collect all problems in a list instead of stopping at the first one. If two things are wrong, the error message shows both, and you fix them in one go.

### Rule 1: no repeated dates

```python
    if df["date"].duplicated().any():
        errors.append("repeated dates")
```

Two methods chained together:

- **`.duplicated()`** returns, for each row, `True` if that date already appeared in a row above, and `False` otherwise.
- **`.any()`** returns `True` if **at least one** value is `True`.

Together: "is there any repeated date?". In loop form:

```python
seen = set()
has_duplicates = False
for d in df["date"]:
    if d in seen:
        has_duplicates = True
    seen.add(d)
```

### Rule 2: no missing days

```python
    expected_days = pd.date_range(start, end, freq="D")
    missing_days = expected_days.difference(df["date"])
    if len(missing_days) > 0:
        errors.append(f"missing days: {[d.date().isoformat() for d in missing_days]}")
```

- **`pd.date_range(start, end, freq="D")`** generates every day that **should** exist in the period (`freq="D"` means daily).
- **`.difference(...)`** returns the days that are in the expected list but **not** in the data. It's the same idea as subtracting sets in Part 4.
- The list comprehension inside the message turns each missing day into readable text, like `2024-03-03`.

### Rule 3: rain is never negative

```python
    if "precipitation_sum" in df.columns and (df["precipitation_sum"] < 0).any():
        errors.append("negative rain")
```

- `"precipitation_sum" in df.columns` checks first if the column exists. If it doesn't, Python doesn't even evaluate the second part of the `and`.
- `df["precipitation_sum"] < 0` compares **every row at once** and returns a column of `True`/`False`. `.any()` asks if any of them is `True`.

> 💡 This "operate on the whole column at once" is called **vectorization**. It replaces the `for` loop you would write in C, and in pandas it is much faster.

### Stopping the pipeline

```python
    if errors:
        raise ValueError("Validation failed: " + "; ".join(errors))
```

An empty list counts as `False`, so this only runs when there is at least one problem. `"; ".join(errors)` glues all messages into one text, separated by `; `.

### Empty values: a warning, not an error

```python
    nulls = int(df.drop(columns=FIXED_COLUMNS).isna().sum().sum())
    if nulls:
        log.warning("%s empty values (the API had no data for them)", nulls)
```

Read it from left to right:

1. `df.drop(columns=FIXED_COLUMNS)` keeps only the weather variables.
2. `.isna()` returns `True` in every cell that is empty.
3. The first `.sum()` counts the `True` values **per column** (`True` counts as 1).
4. The second `.sum()` adds the counts of all columns.
5. `int(...)` turns the result into a regular Python integer.

Why only a warning? It's normal for an API to have no measurement for some day. A whole day **missing** from the answer, on the other hand, signals a real problem. Deciding what is "strange but acceptable" and what is "wrong" is a choice every pipeline has to make. Write that choice down in your project.

---

## Part 6 — Saving as Parquet

```python
# Saves as Parquet, with the same atomic trick as raw_save
def save_staging(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    log.info("staging saved to %s (%s rows)", path, len(df))
```

The structure is the same as `raw_save` from lesson 01: create the folder, write to a temporary file, rename it atomically. Two differences:

- **`df.to_parquet(tmp, index=False)`** writes the table in Parquet format. `index=False` avoids saving the row numbers (0, 1, 2...), which are not real data.
- The log also shows how many rows were saved: `len(df)` is the number of rows in the table.

### Why Parquet and not CSV?

| | CSV | Parquet |
|---|---|---|
| Types | Lost: everything becomes text when you read it back | Kept: dates stay dates, numbers stay numbers |
| Size | Larger | Smaller, because it is compressed |
| Reading one column | Reads the whole file | Reads only that column |
| Opens in a text editor | Yes | No |

The first row is the most important. If you save to CSV and read it back, `date` comes back as text, and you have to declare the schema all over again. With Parquet, the types you declared in Part 4 travel with the data.

This is the **staging layer**: clean, typed, validated data, ready for the next steps.

---

## Part 7 — Running everything

```python
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
```

- The dates must be the same ones used in lesson 01, because they are part of the raw file name.
- `raw_path` is where lesson 01 saved the data; `staging_path` is where this lesson will save it. Same name, different layer and extension.
- The five calls are the five steps of the lesson, in order: read, build the table, enforce the schema, validate, save.
- `print(df.dtypes)` shows the type of each column, so you can confirm that the schema worked.

Run it:

```bash
cd code/02-raw-to-staging
python transform.py
```

You should see the table with 7 rows and, below it, the types:

```
date                 datetime64[ns]
latitude                    float64
longitude                   float64
collected_at    datetime64[ns, UTC]
precipitation_sum           float64
```

Depending on your pandas version, the dates may appear as `datetime64[us]` instead of `[ns]`. Both are dates; only the precision changes. A new file will be in `data/staging/open_meteo/`.

---

## Full code

> The same code is in [`code/02-raw-to-staging/transform.py`](../../code/02-raw-to-staging/transform.py).

```python
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
```

---

## Exercises

1. Open the raw JSON, delete one day from **both** lists, and run the script. Which rule fails?
2. Change one rain value to the text `"lots"` and run it again. Which function stops the program, and why?
3. Save the same DataFrame as CSV with `df.to_csv("test.csv", index=False)`. Compare the file sizes, then read both back with `pd.read_csv` and `pd.read_parquet` and compare `dtypes`.
4. Request `"precipitation_sum,temperature_2m_max"` in lesson 01, run both lessons again, and check that the new column appears without changing this code.

---

[🏠 Index](README.md) · [⬅️ Lesson 01](01-open-meteo-client.md) · [🇧🇷 Português](../pt/02-raw-to-staging.md) · [💻 Code](../../code/02-raw-to-staging/)
