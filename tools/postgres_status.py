"""Observe a private PostgreSQL deployment without exposing its DSN."""

import argparse
import json
import os

from hponas.postgres_operations import postgres_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="hponas")
    args = parser.parse_args()
    dsn = os.environ.get("HPONAS_POSTGRES_DSN")
    if not dsn:
        print(
            json.dumps({"status": "error", "reason": "HPONAS_POSTGRES_DSN is required"})
        )
        return 2
    try:
        result = postgres_status(dsn, schema=args.schema)
    except Exception as exc:
        # No raw driver exception, query or connection string enters the log.
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
