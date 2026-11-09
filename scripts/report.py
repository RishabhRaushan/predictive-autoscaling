"""Render charts and a summary table from results/<source>/*.json."""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from common import MAX_REPLICAS, RESULTS, SLO_P95_SECONDS, load_profile, load_results  # noqa: E402

COLORS = {"static": "#7f8c8d", "reactive": "#e67e22", "scheduled": "#16a085"}


def chart_profile(out):
    profile = load_profile()
    hours = [i * profile["real_bucket_seconds"] / 3600 for i in range(len(profile["rps"]))]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.bar(hours, profile["rps"], width=profile["real_bucket_seconds"] / 3600 * 0.9, align="edge", color="#2c3e50")
    ax.set_xlabel("Hour of recorded day")
    ax.set_ylabel("Requests per second (scaled)")
    ax.set_title("Recorded traffic profile")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def chart_timeline(results, out):
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True)
    first = next(iter(results.values()))
    x = [t / 60 for t in first["t"]]
    a1.fill_between(x, first["rps"], color="#34495e", alpha=0.6)
    a1.set_ylabel("Load (rps)")
    for mode, r in results.items():
        a2.step(x, r["replicas"], where="post", label=mode, color=COLORS[mode], linewidth=2)
        a3.plot(x, [p if p is not None else float("nan") for p in r["p95"]], label=mode, color=COLORS[mode], linewidth=2)
    a2.set_ylabel("Pods")
    a2.set_ylim(0, MAX_REPLICAS + 1)
    a2.legend(loc="upper left", ncol=3)
    a3.axhline(SLO_P95_SECONDS, color="red", linestyle="--", linewidth=1)
    a3.text(0.2, SLO_P95_SECONDS * 1.08, f"SLO {SLO_P95_SECONDS * 1000:.0f} ms", color="red", fontsize=9)
    a3.set_yscale("log")
    a3.set_ylabel("p95 latency (s)")
    a3.set_xlabel("Replay time (minutes; 1 minute = 1 recorded hour)")
    for ax in (a1, a2, a3):
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def chart_comparison(results, out):
    modes = list(results)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 3.8))
    a1.bar(modes, [results[m]["summary"]["pod_minutes"] for m in modes], color=[COLORS[m] for m in modes])
    a1.set_title("Cost proxy: pod-minutes (lower is better)")
    a2.bar(modes, [results[m]["summary"]["slo_violation_pct"] for m in modes], color=[COLORS[m] for m in modes])
    a2.set_title("Time over p95 SLO, % (lower is better)")
    for ax in (a1, a2):
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def write_table(results, out):
    lines = ["| Strategy | Pod-minutes | Cost (USD) | Avg pods | Peak pods | Time over SLO | Worst p95 (s) |", "|---|---|---|---|---|---|---|"]
    for mode, r in results.items():
        s = r["summary"]
        lines.append(f"| {mode} | {s['pod_minutes']} | {s['cost_usd']} | {s['avg_replicas']} | {s['peak_replicas']} | {s['slo_violation_pct']}% | {s['p95_max_s']} |")
    Path(out).write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["simulation", "cluster"], default="simulation")
    args = ap.parse_args()
    results = load_results(args.source)
    if not results:
        raise SystemExit(f"no results in results/{args.source}; run simulate.py or run_experiment.py first")
    out = RESULTS / args.source
    chart_profile(out / "profile.png")
    chart_timeline(results, out / "timeline.png")
    chart_comparison(results, out / "comparison.png")
    write_table(results, out / "summary.md")
    print((out / "summary.md").read_text())
    print(f"charts written to {out}")


if __name__ == "__main__":
    main()
