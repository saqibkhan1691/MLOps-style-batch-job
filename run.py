import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def setup_logging(log_file: str) -> logging.Logger:
    # two handlers - one writes to file, one prints to console so you can watch it live
    logger = logging.getLogger("mlops_task")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s  [%(levelname)s]  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def load_config(config_path: str, logger: logging.Logger) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        cfg = yaml.safe_load(f)

    if cfg is None:
        raise ValueError("Config file is empty or not valid YAML")

    # these three fields are non-negotiable - everything downstream depends on them
    required_fields = ["seed", "window", "version"]
    missing = [field for field in required_fields if field not in cfg]
    if missing:
        raise ValueError(f"Config is missing required fields: {missing}")

    if not isinstance(cfg["seed"], int):
        raise ValueError(f"'seed' must be an integer, got: {type(cfg['seed']).__name__}")
    if not isinstance(cfg["window"], int) or cfg["window"] < 1:
        raise ValueError(f"'window' must be a positive integer, got: {cfg['window']}")
    if not isinstance(cfg["version"], str):
        raise ValueError(f"'version' must be a string, got: {type(cfg['version']).__name__}")

    logger.info(f"Config loaded — seed={cfg['seed']}, window={cfg['window']}, version={cfg['version']}")
    return cfg


def load_dataset(input_path: str, logger: logging.Logger) -> pd.DataFrame:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if path.stat().st_size == 0:
        raise ValueError(f"Input file is empty: {input_path}")

    try:
        df = pd.read_csv(input_path)
    except Exception as e:
        raise ValueError(f"Failed to parse CSV: {e}")

    if df.empty:
        raise ValueError("CSV parsed successfully but contains zero rows")

    # we only care about 'close' for this pipeline, but let's be loud if it's missing
    if "close" not in df.columns:
        raise ValueError(
            f"Required column 'close' not found. Columns present: {list(df.columns)}"
        )

    logger.info(f"Dataset loaded — {len(df)} rows, columns: {list(df.columns)}")
    return df


def compute_rolling_mean(df: pd.DataFrame, window: int, logger: logging.Logger) -> pd.DataFrame:
    # pandas rolling with min_periods=window means the first (window-1) rows get NaN,
    # which is intentional — we skip those rows during signal computation rather than
    # filling with something that might skew the signal rate
    df = df.copy()
    df["rolling_mean"] = df["close"].rolling(window=window, min_periods=window).mean()

    nan_count = df["rolling_mean"].isna().sum()
    logger.info(
        f"Rolling mean computed (window={window}) — {nan_count} warm-up rows excluded from signal"
    )
    return df


def compute_signal(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    df = df.copy()
    # only label rows where we actually have a valid rolling mean
    valid_mask = df["rolling_mean"].notna()

    df["signal"] = np.nan  # default to NaN so we can tell apart "no signal" from signal=0
    df.loc[valid_mask, "signal"] = (
        df.loc[valid_mask, "close"] > df.loc[valid_mask, "rolling_mean"]
    ).astype(int)

    valid_signals = df.loc[valid_mask, "signal"]
    signal_rate = float(valid_signals.mean())
    rows_with_signal = int(valid_signals.count())

    logger.info(
        f"Signal generated — {rows_with_signal} rows with valid signal, "
        f"signal_rate={signal_rate:.6f} "
        f"({int(valid_signals.sum())} rows where close > rolling mean)"
    )
    return df, signal_rate, rows_with_signal


def write_metrics(output_path: str, payload: dict, logger: logging.Logger):
    with open(output_path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Metrics written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="MLOps batch signal pipeline")
    parser.add_argument("--input",    required=True, help="Path to input CSV")
    parser.add_argument("--config",   required=True, help="Path to YAML config")
    parser.add_argument("--output",   required=True, help="Path for output metrics JSON")
    parser.add_argument("--log-file", required=True, help="Path for log file")
    args = parser.parse_args()

    # logger needs to be up before anything else so errors are captured in the log file
    logger = setup_logging(args.log_file)
    logger.info("========== Job started ==========")

    job_start = time.time()
    version = "unknown"  # will be overwritten once config loads

    try:
        # --- step 1: config ---
        cfg = load_config(args.config, logger)
        version = cfg["version"]
        seed    = cfg["seed"]
        window  = cfg["window"]

        # set the seed right after loading config — keeps runs deterministic
        np.random.seed(seed)
        logger.info(f"Random seed set to {seed}")

        # --- step 2: data ---
        df = load_dataset(args.input, logger)

        # --- step 3: rolling mean ---
        df = compute_rolling_mean(df, window, logger)

        # --- step 4: signal ---
        df, signal_rate, rows_processed = compute_signal(df, logger)

        # --- step 5: metrics ---
        latency_ms = int((time.time() - job_start) * 1000)

        metrics = {
            "version":        version,
            "rows_processed": rows_processed,
            "metric":         "signal_rate",
            "value":          round(signal_rate, 4),
            "latency_ms":     latency_ms,
            "seed":           seed,
            "status":         "success",
        }

        write_metrics(args.output, metrics, logger)

        logger.info(
            f"Metrics summary — rows_processed={rows_processed}, "
            f"signal_rate={round(signal_rate, 4)}, latency_ms={latency_ms}"
        )
        logger.info("========== Job finished: SUCCESS ==========")

        # print final JSON to stdout so docker logs show it without extra steps
        print(json.dumps(metrics, indent=2))
        sys.exit(0)

    except Exception as exc:
        latency_ms = int((time.time() - job_start) * 1000)
        logger.error(f"Job failed: {exc}", exc_info=True)
        logger.info("========== Job finished: ERROR ==========")

        error_metrics = {
            "version":       version,
            "status":        "error",
            "error_message": str(exc),
        }

        # always write metrics even on failure so downstream systems have something to parse
        try:
            write_metrics(args.output, error_metrics, logger)
        except Exception as write_exc:
            logger.error(f"Could not write error metrics: {write_exc}")

        print(json.dumps(error_metrics, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()