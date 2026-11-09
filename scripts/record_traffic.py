"""Turn an access log into a replayable traffic profile: N buckets of requests per second."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

TS = re.compile(r"\[(\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}) [+-]\d{4}\]")


def read_timestamps(path):
    stamps = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = TS.search(line)
            if m:
                stamps.append(datetime.strptime(m.group(1), "%d/%b/%Y:%H:%M:%S").timestamp())
    return stamps


def build_profile(stamps, buckets, peak_rps, replay_bucket_seconds, source):
    start, end = min(stamps), max(stamps) + 1
    width = (end - start) / buckets
    counts = [0] * buckets
    for t in stamps:
        counts[min(buckets - 1, int((t - start) / width))] += 1
    peak = max(counts)
    rps = [round(c / peak * peak_rps, 1) for c in counts]
    return {
        "source": source,
        "buckets": buckets,
        "real_bucket_seconds": round(width),
        "replay_bucket_seconds": replay_bucket_seconds,
        "peak_rps": peak_rps,
        "rps": rps,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", default="traffic/sample_access.log")
    ap.add_argument("--out", default="traffic/profile.json")
    ap.add_argument("--buckets", type=int, default=24)
    ap.add_argument("--peak-rps", type=float, default=90, help="RPS of the busiest bucket in the lab cluster")
    ap.add_argument("--replay-bucket-seconds", type=int, default=60, help="wall-clock seconds per bucket (min 60 for cron)")
    args = ap.parse_args()

    stamps = read_timestamps(args.log)
    if not stamps:
        raise SystemExit(f"no timestamps found in {args.log}")
    profile = build_profile(stamps, args.buckets, args.peak_rps, args.replay_bucket_seconds, Path(args.log).name)
    Path(args.out).write_text(json.dumps(profile, indent=2))
    print(f"{len(stamps)} requests -> {args.buckets} buckets, peak {args.peak_rps} rps -> {args.out}")


if __name__ == "__main__":
    main()
