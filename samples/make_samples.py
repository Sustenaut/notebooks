"""Write the offline samples: made-up results shaped like the Site costs queries' real ones.

Nothing here comes from the real call log, which stays private: the projects, plugins and operations are the
ones the repositories declare, and the counts are drawn from a fixed seed, so the files only change when this
script does. Run it from the repository's root: `uv run python samples/make_samples.py`.
"""

import datetime
import random
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
END = datetime.date(2026, 11, 2)
DAYS = 30

# Per project: (plugin, operation, calls a day on average, bytes in, bytes out, typical latency in ms).
TRAFFIC = {
    "integrations": [
        ("slack.post", "post", 40, 900, 400, 180),
        ("github.app-token", "mint", 60, 300, 1200, 220),
        ("cloudflare.dns", "check", 24, 200, 3000, 150),
    ],
    "visit_ee": [
        ("github.edit-pr", "read", 300, 400, 6000, 260),
        ("github.edit-pr", "open-pr", 12, 5000, 2000, 900),
    ],
    "opportunity_site": [
        ("github.app-token", "mint", 20, 300, 1200, 210),
        ("github.edit-pr", "open-pr", 3, 6000, 2000, 950),
    ],
    "business_plan": [
        ("linear.sync", "sync", 96, 800, 9000, 400),
        ("google.bigquery", "query", 30, 1500, 20000, 1200),
        ("slack.post", "post", 8, 900, 400, 170),
    ],
}


def main(seed: int = 2026) -> None:
    rng = random.Random(seed)
    days = [END - datetime.timedelta(days=DAYS - 1 - i) for i in range(DAYS)]
    calls, status = [], []
    for project, traffic in TRAFFIC.items():
        for day in days:
            weekday = day.weekday() < 5
            total = 0
            for plugin, operation, per_day, bytes_in, bytes_out, latency in traffic:
                n = max(0, round(rng.gauss(per_day * (1.15 if weekday else 0.6), per_day * 0.15)))
                if not n:
                    continue
                total += n
                calls.append(
                    {
                        "day": day.isoformat(),
                        "project": project,
                        "plugin": plugin,
                        "operation": operation,
                        "calls": n,
                        "not_ok": sum(rng.random() < 0.01 for _ in range(n)),
                        "bytes_in": n * bytes_in,
                        "bytes_out": n * bytes_out,
                        "p95_latency_ms": round(latency * rng.uniform(1.6, 2.4)),
                    }
                )
            busy = min(720, max(1, round(total / rng.uniform(1.5, 3))))
            status.append(
                {
                    "day": day.isoformat(),
                    "project": project,
                    "sender_cycles": 720,
                    "busy_sender_cycles": busy,
                    "records_sent": total,
                    "drops": 0,
                    "ingest_cycles": 720,
                    "loaded_files": busy,
                    "calls_load_jobs": busy,
                    "status_load_jobs": 720,
                    "max_inbox_bytes": rng.randrange(0, 40_000),
                }
            )
    pd.DataFrame(calls).to_csv(HERE / "calls_per_day.csv", index=False)
    pd.DataFrame(status).to_csv(HERE / "status_per_day.csv", index=False)
    tables = []
    for project in TRAFFIC:
        sent = sum(r["records_sent"] for r in status if r["project"] == project)
        cycles = sum(r["sender_cycles"] + r["ingest_cycles"] for r in status if r["project"] == project)
        tables.append({"project": project, "table_name": "calls", "row_count": sent, "size_bytes": sent * 150})
        tables.append({"project": project, "table_name": "status", "row_count": cycles, "size_bytes": cycles * 110})
    pd.DataFrame(tables).to_csv(HERE / "table_storage.csv", index=False)


if __name__ == "__main__":
    main()
