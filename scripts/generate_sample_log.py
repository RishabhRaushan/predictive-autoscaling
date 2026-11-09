"""Generate a synthetic 24h access log (common log format) with a diurnal curve and an evening flash-sale spike."""
import argparse
import math
import random
from datetime import datetime, timedelta, timezone


def shape(hour):
    diurnal = 0.12 + 0.50 * math.exp(-(((hour - 13.5) / 4.5) ** 2))
    lunch = 0.10 * math.exp(-(((hour - 12.0) / 0.7) ** 2))
    flash = 0.85 * math.exp(-(((hour - 19.4) / 0.9) ** 2))
    return diurnal + lunch + flash


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="traffic/sample_access.log")
    ap.add_argument("--peak-per-minute", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    day = datetime(2026, 11, 9, tzinfo=timezone.utc)
    lines = 0
    with open(args.out, "w", encoding="utf-8") as fh:
        for minute in range(24 * 60):
            rate = shape(minute / 60) * args.peak_per_minute
            count = max(0, round(rng.gauss(rate, math.sqrt(max(rate, 1)))))
            seconds = sorted(rng.randrange(60) for _ in range(count))
            base = day + timedelta(minutes=minute)
            for s in seconds:
                ts = (base + timedelta(seconds=s)).strftime("%d/%b/%Y:%H:%M:%S +0000")
                fh.write(f'10.0.{rng.randrange(256)}.{rng.randrange(256)} - - [{ts}] "GET /work HTTP/1.1" 200 {rng.randrange(80, 200)}\n')
                lines += 1
    print(f"wrote {lines} requests to {args.out}")


if __name__ == "__main__":
    main()
