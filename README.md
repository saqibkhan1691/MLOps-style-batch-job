# MLOps Batch Signal Pipeline

A minimal MLOps-style batch job that loads OHLCV data, computes a rolling mean on `close`, generates a binary trading signal, and outputs structured metrics — all in a reproducible, Dockerized pipeline.

---

## Project structure

```
mlops-task/
├── run.py           # main pipeline script
├── config.yaml      # seed, window, version config
├── data.csv         # input OHLCV dataset (10 000 rows)
├── requirements.txt # pinned Python deps
├── Dockerfile       # single-command Docker build + run
├── metrics.json     # sample output from a successful run
├── run.log          # sample log from a successful run
└── README.md        # you're reading it
```

---

## Local setup

**Prerequisites:** Python 3.9+

```bash
# 1. clone / download the project, then cd into it
cd mlops-task

# 2. create a virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. install dependencies
pip install -r requirements.txt

# 4. run the pipeline
python run.py \
  --input    data.csv \
  --config   config.yaml \
  --output   metrics.json \
  --log-file run.log
```

After the run you'll find:
- `metrics.json` — signal rate, row count, latency
- `run.log` — step-by-step execution log

---

## Docker

```bash
# build the image
docker build -t mlops-task .

# run it (metrics.json + run.log are written inside the container)
docker run --rm mlops-task
```

The final metrics JSON is printed to stdout at the end of every run (success or failure), so `docker logs` always gives you something useful.

If you want the output files on your host machine, mount a volume:

```bash
docker run --rm -v $(pwd)/output:/app mlops-task
# metrics.json and run.log will appear in ./output/
```

---

## Configuration (`config.yaml`)

| Key       | Type   | Description                                     |
|-----------|--------|-------------------------------------------------|
| `seed`    | int    | NumPy random seed — keeps runs deterministic    |
| `window`  | int    | Rolling mean window (number of candles)         |
| `version` | string | Pipeline version tag written into metrics.json  |

---

## Example `metrics.json`

```json
{
  "version": "v1",
  "rows_processed": 9996,
  "metric": "signal_rate",
  "value": 0.499,
  "latency_ms": 134,
  "seed": 42,
  "status": "success"
}
```

> **Note on `rows_processed`:** with `window=5`, the first 4 rows don't have a complete rolling window, so they're excluded from signal computation. That leaves 9 996 valid signal rows out of 10 000.

---

## Error handling

The pipeline validates:
- Config file exists and contains `seed`, `window`, `version`
- Input CSV exists, is non-empty, and contains a `close` column
- All config values are the correct types

On any failure, `metrics.json` is still written with `"status": "error"` and a human-readable `error_message`, and the process exits with code 1.

---

## Signal logic

```
rolling_mean[i] = mean(close[i-window+1 : i+1])   # NaN for first (window-1) rows
signal[i]       = 1  if close[i] > rolling_mean[i]
                  0  otherwise
                  (excluded if rolling_mean[i] is NaN)
```