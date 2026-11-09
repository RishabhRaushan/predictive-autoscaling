"""Run static / reactive / scheduled scaling against the same replayed traffic on a live cluster and collect results."""
import argparse
import contextlib
import json
import math
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import (  # noqa: E402
    DEPLOYMENT, MIN_REPLICAS, NAMESPACE, ROOT, SAMPLE_STEP_SECONDS, load_profile, replicas_for, save_result, summarize,
    RESULTS,
)
from generate_schedule import build_manifest  # noqa: E402

PROM_NS = "monitoring"
PROM_SVC = "kube-prometheus-stack-prometheus"
PROM_URL = "http://localhost:9090"
SEL = f'namespace="{NAMESPACE}",job="{DEPLOYMENT}"'
QUERIES = {
    "rps": f"sum(rate(http_requests_total{{{SEL}}}[30s]))",
    "p95": f"histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{SEL}}}[30s])))",
    "replicas": f'kube_deployment_status_replicas{{namespace="{NAMESPACE}",deployment="{DEPLOYMENT}"}}',
    "ready": f'kube_deployment_status_replicas_available{{namespace="{NAMESPACE}",deployment="{DEPLOYMENT}"}}',
}


def kubectl(*args, stdin=None, check=True):
    return subprocess.run(["kubectl", *args], input=stdin, text=True, capture_output=True, check=check)


def apply_yaml(text):
    kubectl("apply", "-f", "-", stdin=text)


def apply_file(path):
    kubectl("apply", "-f", str(path))


def require_cluster():
    for crd in ("scaledobjects.keda.sh", "servicemonitors.monitoring.coreos.com"):
        if kubectl("get", "crd", crd, check=False).returncode != 0:
            raise SystemExit(f"CRD {crd} not found. Run 'terraform apply' first (see README).")


@contextlib.contextmanager
def prometheus_port_forward():
    proc = subprocess.Popen(
        ["kubectl", "-n", PROM_NS, "port-forward", f"svc/{PROM_SVC}", "9090:9090"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(30):
            try:
                urllib.request.urlopen(f"{PROM_URL}/-/ready", timeout=2)
                break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit("Prometheus port-forward did not become ready")
        yield
    finally:
        proc.terminate()


def prom_range(query, start, end, step):
    qs = urllib.parse.urlencode({"query": query, "start": start, "end": end, "step": step})
    with urllib.request.urlopen(f"{PROM_URL}/api/v1/query_range?{qs}", timeout=30) as resp:
        result = json.load(resp)["data"]["result"]
    if not result:
        return {}
    return {int(float(t)): float(v) for t, v in result[0]["values"] if not math.isnan(float(v))}


def collect(t0, duration):
    step = SAMPLE_STEP_SECONDS
    stamps = list(range(t0, t0 + duration, step))
    raw = {name: prom_range(q, t0, t0 + duration - step, step) for name, q in QUERIES.items()}
    series = {"t": [s - t0 for s in stamps], "rps": [], "p95": [], "replicas": [], "ready": []}
    last = {"replicas": MIN_REPLICAS, "ready": MIN_REPLICAS}
    for s in stamps:
        series["rps"].append(round(raw["rps"].get(s, 0.0), 2))
        series["p95"].append(round(raw["p95"][s], 3) if s in raw["p95"] else None)
        for key in ("replicas", "ready"):
            last[key] = int(raw[key].get(s, last[key]))
            series[key].append(last[key])
    return series


def reset(mode, static_replicas):
    kubectl("-n", NAMESPACE, "delete", "scaledobject", "--all", "--ignore-not-found")
    kubectl("-n", NAMESPACE, "delete", "job", "k6-replay", "--ignore-not-found")
    replicas = static_replicas if mode == "static" else MIN_REPLICAS
    kubectl("-n", NAMESPACE, "scale", f"deploy/{DEPLOYMENT}", f"--replicas={replicas}")
    kubectl("-n", NAMESPACE, "rollout", "status", f"deploy/{DEPLOYMENT}", "--timeout=180s")


def start_replay(t0, bucket):
    cm = kubectl(
        "-n", NAMESPACE, "create", "configmap", "k6-replay",
        f"--from-file=replay.js={ROOT / 'k6' / 'replay.js'}",
        f"--from-file=profile.json={ROOT / 'traffic' / 'profile.json'}",
        "--dry-run=client", "-o", "yaml",
    ).stdout
    apply_yaml(cm)
    job = (ROOT / "k8s" / "k6-job.yaml.tpl").read_text()
    job = job.replace("__START_EPOCH_MS__", str(t0 * 1000)).replace("__BUCKET_SECONDS__", str(bucket))
    apply_yaml(job)


def wait_for_job(deadline):
    while time.time() < deadline:
        out = kubectl("-n", NAMESPACE, "get", "job", "k6-replay", "-o", "jsonpath={.status.succeeded}/{.status.failed}").stdout
        ok, _, failed = out.partition("/")
        if ok == "1":
            return "passed"
        if failed and failed != "0":
            return "thresholds-failed-or-error"  # k6 exits non-zero when a threshold is crossed
        time.sleep(10)
    raise SystemExit("timed out waiting for k6")


def run_mode(mode, profile):
    bucket = profile["replay_bucket_seconds"]
    duration = len(profile["rps"]) * bucket
    print(f"\n=== {mode}: {duration}s replay ===")
    reset(mode, replicas_for(max(profile["rps"])))

    t0 = (int(time.time()) // 60) * 60 + 120  # minute-aligned so cron windows match bucket edges
    if mode == "reactive":
        apply_file(ROOT / "k8s" / "scaledobject-reactive.yaml")
    elif mode == "scheduled":
        apply_yaml(build_manifest(profile, t0))
    start_replay(t0, bucket)

    status = wait_for_job(t0 + duration + 300)
    logs = kubectl("-n", NAMESPACE, "logs", "job/k6-replay", check=False).stdout
    (RESULTS / "cluster").mkdir(parents=True, exist_ok=True)
    (RESULTS / "cluster" / f"k6-{mode}.log").write_text(logs)
    time.sleep(20)  # let the last scrapes land

    series = collect(t0, duration)
    result = {
        "source": "cluster", "mode": mode, "step": SAMPLE_STEP_SECONDS, "k6": status, "t0": t0, **series,
        "summary": summarize(SAMPLE_STEP_SECONDS, series["rps"], series["replicas"], series["p95"]),
    }
    save_result("cluster", mode, result)
    print(json.dumps(result["summary"], indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--modes", nargs="+", default=["static", "reactive", "scheduled"], choices=["static", "reactive", "scheduled"])
    ap.add_argument("--image", default="demo-app:1.0", help="app image, e.g. an ECR URI when running on AWS")
    args = ap.parse_args()

    require_cluster()
    for f in ("namespace.yaml", "servicemonitor.yaml"):
        apply_file(ROOT / "k8s" / f)
    apply_yaml((ROOT / "k8s" / "app.yaml").read_text().replace("image: demo-app:1.0", f"image: {args.image}"))
    profile = load_profile()
    with prometheus_port_forward():
        for mode in args.modes:
            run_mode(mode, profile)
    kubectl("-n", NAMESPACE, "delete", "scaledobject", "--all", "--ignore-not-found")
    print("\nDone. Next: python scripts/report.py --source cluster")


if __name__ == "__main__":
    main()
