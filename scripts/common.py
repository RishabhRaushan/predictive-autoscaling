"""Shared constants and helpers. Keep in sync with k8s/*.yaml and app/main.py."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
PROFILE_PATH = ROOT / "traffic" / "profile.json"

NAMESPACE = "autoscale-lab"
DEPLOYMENT = "demo-app"
THRESHOLD_RPS_PER_POD = 15  # scaling target (60% of capacity)
CAPACITY_RPS_PER_POD = 25  # 20 ms CPU per request, 500m CPU limit
MIN_REPLICAS = 2
MAX_REPLICAS = 12
PRICE_PER_POD_HOUR = 0.04  # illustrative USD, change to match your instance pricing
SLO_P95_SECONDS = 0.5
SAMPLE_STEP_SECONDS = 15


def load_profile(path=None):
    return json.loads(Path(path or PROFILE_PATH).read_text())


def replicas_for(rps):
    return min(MAX_REPLICAS, max(MIN_REPLICAS, math.ceil(rps / THRESHOLD_RPS_PER_POD)))


def summarize(step, rps, replicas, p95):
    """Cost and SLO summary shared by simulator and cluster runs."""
    pod_minutes = sum(replicas) * step / 60
    active = [p for r, p in zip(rps, p95) if r is not None and r > 0.5 and p is not None]
    violations = sum(1 for p in active if p > SLO_P95_SECONDS)
    return {
        "pod_minutes": round(pod_minutes, 2),
        "cost_usd": round(pod_minutes / 60 * PRICE_PER_POD_HOUR, 4),
        "avg_replicas": round(sum(replicas) / len(replicas), 2),
        "peak_replicas": max(replicas),
        "slo_violation_pct": round(100 * violations / len(active), 1) if active else 0.0,
        "p95_max_s": round(max(active), 3) if active else 0.0,
        "samples": len(replicas),
    }


def save_result(source, mode, data):
    out = RESULTS / source
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{mode}.json").write_text(json.dumps(data, indent=2))


def load_results(source):
    order = ["static", "reactive", "scheduled"]
    found = {}
    for mode in order:
        path = RESULTS / source / f"{mode}.json"
        if path.exists():
            found[mode] = json.loads(path.read_text())
    return found
