# For Beginners: Using the Open-Meteo API to Practice Data Engineering

[🏠 Index](README.md) · [🇧🇷 Português](../pt/01-open-meteo-client.md) · [💻 Code](../../code/01-open-meteo-client/)

---

## What you will learn

- [ ] Which libraries we need and why
- [ ] How to create a session that retries automatically when the API fails
- [ ] How to make a safe request (timeout, logging, error checking)
- [ ] How to save the raw response to a file
- [ ] How to request daily rainfall from Open-Meteo
- [ ] How to run everything together

## Before you start

You need **Python 3.10 or newer** (we use the `dict | None` syntax, which only exists from 3.10 on) and the `requests` library:

```bash
pip install requests
```

The Open-Meteo historical API is free for non-commercial use and **does not need an API key**. That makes it a great first API: you can focus on writing good code instead of fighting authentication.

---

## Part 1 — Libraries

```python
import requests
import os
import time
import logging
import json

from pathlib import Path
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from datetime import datetime, timezone, date
```

- **`requests`** sends HTTP requests to the API. It is the most popular library for this in Python.
- **`os`** reads environment variables. We use it to read a secret token, if one exists, without writing it in the code.
- **`time`** measures how long each request takes.
- **`logging`** writes messages about what the program is doing (a better, more professional version of `print`).
- **`json`** converts Python dictionaries into JSON text, so we can save them to a file.
- **`Path`** (from `pathlib`) represents file and folder paths. It works the same way on Windows and Linux.
- **`Retry`** (from `urllib3`) defines the rules for trying a request again when it fails.
- **`HTTPAdapter`** (from `requests.adapters`) connects those retry rules to our session.
- **`datetime`, `timezone`, `date`** handle dates and times: when the data was collected and which days we want.

> 💡 `urllib3` is installed automatically with `requests`, because `requests` uses it internally. You don't need to install it separately.

---

## Part 2 — Settings

```python
TIMEOUT_S = 30
```

The maximum number of seconds we wait for the API to answer. The name is in CAPITAL LETTERS because it is a **constant**: a value we define once and don't change while the program runs. The `_S` at the end reminds us that the unit is seconds.

> ⚠️ By default, `requests` waits **forever**. If the API stops answering, your program freezes. Always use a timeout.

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger("api.client")
```

- `basicConfig` configures logging once for the whole program.
- `level=logging.INFO` means "show messages of level INFO or higher". Without it, the default level is WARNING, and our `log.info(...)` messages would not appear.
- `format` defines what each line looks like: date and time, logger name, level, and message.
- `getLogger("api.client")` creates a logger with a name, so we know which part of the program wrote each message.

> ⚠️ `basicConfig` only accepts **named arguments** (`format=...`, `level=...`). Writing `logging.basicConfig("%(asctime)s ...")` without `format=` causes a `TypeError`.

A log line will look like this:

```
2026-09-24 10:15:02,123 - api.client - INFO - GET https://archive-api... status=200 duration=0.41s
```

---

## Part 3 — Creating the session

```python
def session_maker() -> requests.Session:
    session = requests.Session()
```

A **session** is an object that keeps settings (headers, retry rules) and reuses the same connection across many requests. It is faster than calling `requests.get` directly every time, and we configure everything in a single place.

`-> requests.Session` is a **type hint**: it tells the reader that this function returns a session. Python doesn't check it at runtime; it exists for people and for tools like your editor.

> 💡 Variable names in Python are written in lowercase (`session`, not `Session`). Capitalized names are used for classes, like `requests.Session`. This convention comes from PEP 8, Python's style guide.

### Retry rules

```python
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
```

- **`total=5`**: try again up to 5 times.
- **`backoff_factor=1`**: wait longer after each failure (roughly 1, 2, 4, 8 seconds). This is called **exponential backoff**. It gives the server time to recover instead of hitting it again immediately.
- **`status_forcelist`**: the HTTP status codes that deserve a retry. All of them are **temporary** errors:
  - `429` — Too Many Requests: we went over the API's limit.
  - `500`, `502`, `503`, `504` — server errors: the problem is on their side.
- **`allowed_methods=["GET"]`**: only retry GET requests. GET only reads data, so repeating it is safe.

We do **not** retry errors like `400` (bad request), `401` (not authorized) or `404` (not found). Those are **our** mistakes, and trying again won't fix them.

> 💡 If the API sends a `Retry-After` header ("wait X seconds"), `Retry` respects it automatically.

### Attaching the rules to the session

```python
    session.mount("https://", HTTPAdapter(max_retries=retry))
```

`HTTPAdapter` is the part of `requests` that actually sends requests. Here we create one with our retry rules and **mount** it on the session: every URL that starts with `https://` will use it.

### Headers

```python
    session.headers.update({
        "User-Agent": "estudo-engenharia-dados/0.1 (youremail@example.com)",
        "Accept": "application/json",
    })
```

Headers are extra information sent with every request.

- **`User-Agent`** identifies who is calling: the project name, version and a contact. It is good manners with public APIs, and some APIs require it. **Use your own email here.**
- **`Accept: application/json`** tells the API we want the answer in JSON.

### Optional token

```python
    token = os.environ.get("API_TOKEN")
    if token:
        session.headers["chave-api-dados"] = token

    return session
```

`os.environ.get("API_TOKEN")` reads the environment variable `API_TOKEN`. If it doesn't exist, it returns `None`, and the `if` is skipped.

Open-Meteo doesn't need a token, so this part does nothing here. It is in the function so you can reuse it with APIs that do, like Brazil's Portal da Transparência, which expects the key in a header called `chave-api-dados`. For another API, change the header name to the one its documentation asks for.

> ⚠️ Never write a token directly in your code. If you push it to GitHub, anyone can use it.

---

## Part 4 — Making a safe request

```python
def get_json(session: requests.Session, url: str, params: dict | None = None) -> dict:
```

The function receives:

- **`session`**: the session we created in Part 3;
- **`url`**: the API address (a string);
- **`params`**: the query parameters, as a dictionary. `dict | None = None` means it can be a dictionary **or** `None`, and it is `None` if we don't pass anything, so it is optional.

It returns a dictionary (`-> dict`).

> 💡 Why `= None` and not `= {}`? In Python, a default value is created only **once**, when the function is defined. A mutable default like `{}` would be shared between calls and can cause strange bugs. Using `None` is the standard way to avoid that.

### Sending the request and measuring the time

```python
    start = time.perf_counter()
    resp = session.get(url, params=params, timeout=TIMEOUT_S)
    duration = round(time.perf_counter() - start, 2)
```

- `time.perf_counter()` is a precise stopwatch. We read it before and after the request.
- `session.get(...)` sends the GET request. `requests` turns the `params` dictionary into the part of the URL after the `?`, for example `?latitude=-16.72&longitude=-43.86`.
- `duration` is the difference between the two readings, rounded to 2 decimal places.

### Logging

```python
    log.info("GET %s status=%s duration=%ss", resp.url, resp.status_code, duration)
```

We log the full URL, the status code and the duration. Two details:

- We use `resp.url` instead of `url` because `resp.url` includes the parameters. That shows exactly what was requested.
- The `%s` placeholders are filled in by `logging` itself. This is the recommended style for logs, instead of f-strings.

> ⚠️ Don't log headers: that's where the token lives. And if an API puts the key **in the URL**, don't log the URL either.

### Checking for errors

```python
    resp.raise_for_status()
```

If the status code is an error (4xx or 5xx) that is still there after all retries, this line raises an exception and stops the program. Failing loudly is better than silently continuing with bad data.

```python
    if "json" not in resp.headers.get("Content-Type", ""):
        raise ValueError(f"Response is not JSON: {resp.headers.get('Content-Type')}")
```

Some APIs return an HTML error page with status `200` (success!). Here we check the `Content-Type` header: if it doesn't mention JSON, we stop. The `""` in `.get("Content-Type", "")` is a default value, used if the header doesn't exist.

> 💡 Header names in `requests` are case-insensitive: `"Content-Type"` and `"Content-type"` find the same header.

### Returning data and metadata

```python
    return {
        "meta": {
            "url": resp.url,
            "status": resp.status_code,
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duration_s": duration,
        },
        "body": resp.json(),
    }
```

We return two things:

- **`meta`**: information **about** the request: which URL, which status, **when** it was collected and how long it took. `datetime.now(timezone.utc)` uses UTC, so the time doesn't depend on where the code runs.
- **`body`**: the API's answer, converted from JSON text into a Python dictionary by `resp.json()`.

Keeping the metadata makes it possible to answer later: "when did I download this, and from where?"

---

## Part 5 — Saving the raw response

```python
def raw_save(content: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    log.info("raw saved to %s", path)
```

In data engineering, the **raw layer** stores the data exactly as it came from the source. If a later step has a bug, we reprocess from the raw file without calling the API again.

Line by line:

- **`path.parent.mkdir(parents=True, exist_ok=True)`** creates the folder where the file will live. `parents=True` also creates any missing folders above it; `exist_ok=True` doesn't complain if the folder already exists.
- **`tmp = path.with_suffix(".tmp")`** creates a temporary file name: `data.json` → `data.tmp`.
- **`json.dumps(...)`** converts the dictionary into JSON text. `ensure_ascii=False` keeps accents readable (`ç`, `ã`); `indent=2` formats it nicely.
- **`tmp.write_text(..., encoding="utf-8")`** writes the text to the temporary file.
- **`tmp.replace(path)`** renames the temporary file to the final name. Renaming is **atomic**: it either happens completely or not at all. If the program crashes in the middle of writing, the old file stays intact, and you never get a half-written file.
- The `-> None` means the function doesn't return anything; it only does something.

> ⚠️ Common mistake: calling `.parent` or `.with_suffix` on `content` instead of `path`. `content` is a dictionary, and dictionaries don't have those methods, so you get an `AttributeError`. The folder and the file name always come from `path`.

---

## Part 6 — Asking Open-Meteo for rain data

```python
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
```

This function knows **what** to ask Open-Meteo. The **how** (retries, timeout, checks) stays in `get_json`. Separating those two responsibilities means you can write a new function for another API and reuse `get_json` as it is.

The parameters sent to the API:

| Parameter | Meaning |
|---|---|
| `latitude`, `longitude` | The location. Negative values are south and west. |
| `start_date`, `end_date` | The period, in `YYYY-MM-DD` format. `.isoformat()` turns a `date` into that text. |
| `daily` | Which daily variable we want. `precipitation_sum` is the total rain of the day, in mm. |
| `timezone` | Which timezone defines where "a day" starts and ends. |

The function receives the dates as **parameters** instead of using fixed dates. That's what makes it reusable: the same function downloads one day, one week, or ten years (this is called a **backfill**).

---

## Part 7 — Running everything

```python
if __name__ == "__main__":
    session = session_maker()

    start, end = date(2024, 3, 1), date(2024, 3, 7)
    weather = open_meteo_rain(session, -16.72, -43.86, start, end)
    raw_save(weather, Path(f"data/raw/open_meteo/{start}_{end}.json"))

    daily = weather["body"]["daily"]
    for day, rain in zip(daily["time"], daily["precipitation_sum"]):
        print(f"{day}: {rain} mm")
```

- **`if __name__ == "__main__":`** — this block only runs when you execute the file directly (`python client.py`). If another file imports these functions, this block is skipped.
- **`session_maker()`** creates the session once.
- **`start, end = ...`** defines the period: the first week of March 2024.
- **`open_meteo_rain(...)`** requests rain for Montes Claros, MG (latitude -16.72, longitude -43.86).
- **`raw_save(...)`** saves the answer to `data/raw/open_meteo/2024-03-01_2024-03-07.json`. Putting the dates in the file name makes each period easy to find.
- **`weather["body"]["daily"]`** opens the part of the answer with the daily data. It contains two lists of the same size: `time` (the days) and `precipitation_sum` (the rain).
- **`zip(...)`** walks through both lists together, pairing each day with its rain.

Run it from the repository root:

```bash
cd code/01-open-meteo-client
python client.py
```

You should see log lines followed by one line per day, in the format `2024-03-01: X.X mm`, and a new JSON file in `data/raw/open_meteo/`.

---

## Full code

> The same code is in [`code/01-open-meteo-client/client.py`](../../code/01-open-meteo-client/client.py).

```python
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
```

---

## Exercises

1. Change the coordinates to your own city and download a whole month.
2. Add `"temperature_2m_max"` to the `daily` parameter (separate variables with a comma: `"precipitation_sum,temperature_2m_max"`) and print both values.
3. Pass a date in the wrong format directly in the URL and see what `raise_for_status()` does.
4. Write a new function, `bcb_series(session, code, start, end)`, for the Banco Central API, reusing `session_maker` and `get_json` without changing them.

---

[🏠 Index](README.md) · [🇧🇷 Português](../pt/01-open-meteo-client.md) · [💻 Code](../../code/01-open-meteo-client/)
