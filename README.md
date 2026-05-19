# MLOps Batch Signal Pipeline

A production-style MLOps batch job that ingests raw OHLCV market data, computes a rolling mean strategy on Bitcoin close prices, emits binary trading signals, and writes machine-readable metrics — all in a single deterministic, fully Dockerized run.

Built as part of the MetaStackerBandit trading-signal pipeline internship assessment at Primetrade.ai.

---

## Table of Contents

1. Overview
2. Architecture and Workflow
3. Project Structure
4. Prerequisites
5. Local Setup and Run
6. Docker Setup and Run
7. Configuration Reference
8. Output Reference
9. Signal Logic Explained
10. Error Handling
11. Sample Output
12. Tech Stack

---

## Overview

This pipeline demonstrates three core MLOps principles in a compact, readable codebase.

**Reproducibility** — every run with the same config and seed produces byte-identical output. No randomness leaks between runs.

**Observability** — a structured JSON metrics file and a timestamped human-readable log are written on every run, including failure cases. Nothing silently disappears.

**Deployment Readiness** — the entire job runs inside a Docker container with a single command. No environment setup, no path assumptions, no host dependencies.

---

## Architecture and Workflow

```
config.yaml          data.csv
     |                   |
     v                   v
  Load and           Load and
  Validate           Validate
  Config              Dataset
     |                   |
     +------- merge ------+
                  |
                  v
           Set NumPy Seed
           (determinism)
                  |
                  v
         Compute Rolling Mean
         on close (window=5)
         first 4 rows = NaN
                  |
                  v
         Generate Binary Signal
         1 if close > rolling_mean
         0 otherwise
         NaN rows excluded
                  |
                  v
        Compute Metrics
        rows_processed
        signal_rate
        latency_ms
                  |
          +-------+-------+
          |               |
          v               v
     metrics.json      run.log
     (JSON output)   (log output)
          |
          v
     stdout print
     (Docker visible)
```

---

## Project Structure

```
mlops-task/
  run.py              main pipeline script with all logic
  config.yaml         seed, window, version config
  data.csv            10000-row OHLCV Bitcoin dataset
  requirements.txt    pinned Python dependencies
  Dockerfile          single-command Docker build and run
  metrics.json        sample output from a successful run
  run.log             sample log from a successful run
  README.md           this file
```

---

## Prerequisites

**For local run:**
- Python 3.9 or higher
- pip

**For Docker run:**
- Docker Desktop (Windows or Mac) or Docker Engine (Linux)

---

## Local Setup and Run

**Step 1 — Clone or download the project**

```bash
cd mlops-task
```

**Step 2 — Create a virtual environment**

```bash
python -m venv .venv
```

**Step 3 — Activate the virtual environment**

```bash
# Windows
.venv\Scripts\activate

# Mac or Linux
source .venv/bin/activate
```

**Step 4 — Install dependencies**

```bash
pip install -r requirements.txt
```

**Step 5 — Run the pipeline**

```bash
python run.py --input data.csv --config config.yaml --output metrics.json --log-file run.log
```

**Step 6 — Check the outputs**

```bash
# View metrics
type metrics.json        # Windows
cat metrics.json         # Mac or Linux

# View logs
type run.log             # Windows
cat run.log              # Mac or Linux
```

---

## Docker Setup and Run

**Step 1 — Build the image**

```bash
docker build -t mlops-task .
```

This downloads the base image and installs all dependencies inside the container. Takes 1 to 2 minutes on first run.

**Step 2 — Run the container**

```bash
docker run --rm mlops-task
```

The final metrics JSON is printed to stdout automatically. Exit code 0 means success, non-zero means failure.

**Optional — Copy output files to your machine**

```bash
docker run --rm -v ${PWD}/output:/app mlops-task
```

After this, metrics.json and run.log will appear in the output folder on your host machine.

---

## Configuration Reference

All pipeline behavior is controlled through config.yaml. No values are hardcoded in run.py.

| Field   | Type   | Description                                              |
|---------|--------|----------------------------------------------------------|
| seed    | int    | NumPy random seed. Ensures identical output every run.   |
| window  | int    | Rolling mean window in number of candles.                |
| version | string | Pipeline version tag. Written into every metrics.json.   |

Example config.yaml:

```yaml
seed: 42
window: 5
version: "v1"
```

---

## Output Reference

**metrics.json on success**

```json
{
  "version": "v1",
  "rows_processed": 9996,
  "metric": "signal_rate",
  "value": 0.4991,
  "latency_ms": 24,
  "seed": 42,
  "status": "success"
}
```

**metrics.json on error**

```json
{
  "version": "v1",
  "status": "error",
  "error_message": "Required column close not found. Columns present: [...]"
}
```

The metrics file is always written even when the job fails so downstream systems always have something parseable.

---

## Signal Logic Explained

The pipeline computes a rolling mean using a configurable window size. For a window of 5, the mean at position i is the average of close prices from position i-4 through i.

The first 4 rows (window minus 1) do not have enough preceding data to form a complete window. These rows receive NaN for their rolling mean and are excluded from signal computation entirely. This is intentional — filling warm-up rows with partial averages would skew the signal rate.

```
rolling_mean[i]  =  mean of close[i-4] through close[i]    (NaN for i < 4)

signal[i]  =  1   if close[i] > rolling_mean[i]
              0   if close[i] <= rolling_mean[i]
              excluded if rolling_mean[i] is NaN
```

With 10000 total rows and window=5, the pipeline processes 9996 valid signal rows.

---

## Error Handling

The pipeline validates every input before processing and writes an error metrics file on any failure.

Validated conditions:

- Config file exists on disk
- Config contains all required fields: seed, window, version
- seed is an integer
- window is a positive integer
- version is a string
- Input CSV file exists on disk
- Input CSV file is not empty
- Input CSV parses without errors
- Parsed CSV contains at least one row
- CSV contains a close column

On any validation failure the job logs the full traceback, writes metrics.json with status error and a human-readable error_message, prints the error JSON to stdout, and exits with code 1.

---

## Sample Output

**Terminal output after a successful run:**

```
2026-05-19 08:51:52  [INFO]  ========== Job started ==========
2026-05-19 08:51:52  [INFO]  Config loaded   seed=42, window=5, version=v1
2026-05-19 08:51:52  [INFO]  Random seed set to 42
2026-05-19 08:51:52  [INFO]  Dataset loaded   10000 rows
2026-05-19 08:51:52  [INFO]  Rolling mean computed (window=5)   4 warm-up rows excluded
2026-05-19 08:51:52  [INFO]  Signal generated   9996 rows, signal_rate=0.499100
2026-05-19 08:51:52  [INFO]  Metrics written to metrics.json
2026-05-19 08:51:52  [INFO]  Metrics summary   rows_processed=9996, signal_rate=0.4991, latency_ms=24
2026-05-19 08:51:52  [INFO]  ========== Job finished: SUCCESS ==========

{
  "version": "v1",
  "rows_processed": 9996,
  "metric": "signal_rate",
  "value": 0.4991,
  "latency_ms": 24,
  "seed": 42,
  "status": "success"
}
```

---

## Tech Stack

| Layer        | Technology             |
|--------------|------------------------|
| Language     | Python 3.9             |
| Data         | pandas 2.2.2           |
| Numerics     | numpy 1.26.4           |
| Config       | PyYAML 6.0.1           |
| Container    | Docker python:3.9-slim |
| Logging      | Python standard logging|

---

## Author

Built by Saqib Khan

Crafted with attention to clean code, production-grade structure, and real MLOps principles.
