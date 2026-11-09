"""Second-by-second model of static, reactive (KEDA+Prometheus) and scheduled (KEDA cron) scaling. No cluster needed."""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (  # noqa: E402
    CAPACITY_RPS_PER_POD, MAX_REPLICAS, MIN_REPLICAS, SAMPLE_STEP_SECONDS, THRESHOLD_RPS_PER_POD,
    load_profile, replicas_for, save_result, summarize,
)
from generate_schedule import plan_replicas  # noqa: E402

POLL = 15  # KEDA pollingInterval / HPA sync period
STARTUP = 15  # seconds from scale decision to a ready pod
METRIC_LAG = 10  # Prometheus scrape + rule evaluation delay
RATE_WINDOW = 60  # rate(...[1m])
SCALE_DOWN_WINDOW = 60  # HPA stabilization for the reactive ScaledObject
RAMP = 5  # k6 ramps over 5s at each bucket boundary


def rps_per_second(profile):
    out, prev = [], profile["rps"][0]
    for r in profile["rps"]:
        for s in range(profile["replay_bucket_seconds"]):
            out.append(prev + (r - prev) * min(1.0, (s + 1) / RAMP))
        prev = r
    return out


def simulate(mode, profile, lookahead=1):
    load = rps_per_second(profile)
    bucket = profile["replay_bucket_seconds"]
    schedule = plan_replicas(profile["rps"], lookahead)
    static_n = replicas_for(max(profile["rps"]))

    ready = static_n if mode == "static" else MIN_REPLICAS
    starting = []  # (ready_at, count)
    recommendations = []  # (t, desired) for scale-down stabilization
    backlog = 0.0
    acc = {"rps": [], "replicas": [], "ready": [], "p95": []}
    window = {"rps": [], "ready": [], "total": [], "p95": []}

    for t, arriving in enumerate(load):
        ready += sum(n for at, n in starting if at <= t)
        starting = [(at, n) for at, n in starting if at > t]
        total = ready + sum(n for _, n in starting)

        if mode != "static" and t % POLL == 0:
            if mode == "reactive":
                lo, hi = max(0, t - METRIC_LAG - RATE_WINDOW), max(1, t - METRIC_LAG)
                seen = load[lo:hi]
                raw = replicas_for(sum(seen) / len(seen))
                recommendations.append((t, raw))
                desired = max(d for at, d in recommendations if t - at <= SCALE_DOWN_WINDOW)
                desired = raw if raw > total else desired
            else:
                desired = schedule[min(len(schedule) - 1, t // bucket)]
            desired = min(MAX_REPLICAS, max(MIN_REPLICAS, desired))
            if desired > total:
                starting.append((t + STARTUP, desired - total))
            elif desired < total:
                cut = total - desired
                while cut and starting:
                    at, n = starting.pop()
                    drop = min(n, cut)
                    if n > drop:
                        starting.append((at, n - drop))
                    cut -= drop
                ready = max(1, ready - cut)
            total = ready + sum(n for _, n in starting)

        capacity = ready * CAPACITY_RPS_PER_POD
        backlog = max(0.0, backlog + arriving - capacity)
        rho = arriving / capacity
        p95 = min(30.0, 0.12 / max(0.05, 1 - rho) + backlog / capacity) if rho < 1 or backlog else 30.0

        window["rps"].append(arriving)
        window["ready"].append(ready)
        window["total"].append(total)
        window["p95"].append(p95)
        if (t + 1) % SAMPLE_STEP_SECONDS == 0:
            acc["rps"].append(round(sum(window["rps"]) / len(window["rps"]), 2))
            acc["ready"].append(window["ready"][-1])
            acc["replicas"].append(window["total"][-1])
            acc["p95"].append(round(sum(window["p95"]) / len(window["p95"]), 3))
            window = {k: [] for k in window}

    return {
        "source": "simulation",
        "mode": mode,
        "step": SAMPLE_STEP_SECONDS,
        "t": [i * SAMPLE_STEP_SECONDS for i in range(len(acc["rps"]))],
        **acc,
        "summary": summarize(SAMPLE_STEP_SECONDS, acc["rps"], acc["replicas"], acc["p95"]),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--lookahead", type=int, default=1)
    args = ap.parse_args()
    profile = load_profile(args.profile)
    print(f"{'mode':<10}{'pod-min':>9}{'cost $':>9}{'avg pods':>10}{'SLO viol %':>12}{'max p95 s':>11}")
    for mode in ("static", "reactive", "scheduled"):
        result = simulate(mode, profile, args.lookahead)
        save_result("simulation", mode, result)
        s = result["summary"]
        print(f"{mode:<10}{s['pod_minutes']:>9}{s['cost_usd']:>9}{s['avg_replicas']:>10}{s['slo_violation_pct']:>12}{s['p95_max_s']:>11}")


if __name__ == "__main__":
    main()
