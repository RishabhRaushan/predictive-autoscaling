"""Demo service: each /work request burns a fixed amount of CPU time so capacity per pod is predictable."""
import os
import time

from flask import Flask, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

WORK_MS = float(os.getenv("WORK_MS", "20"))

app = Flask(__name__)

REQUESTS = Counter("http_requests", "Total /work requests", ["status"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Latency of /work requests",
    buckets=(0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1, 2, 5, 10),
)


def burn_cpu(ms: float) -> None:
    # thread_time counts only CPU actually received, so cgroup throttling stretches latency like real load.
    deadline = time.thread_time() + ms / 1000.0
    x = 0
    while time.thread_time() < deadline:
        x += 1


@app.route("/work")
def work():
    start = time.perf_counter()
    burn_cpu(WORK_MS)
    LATENCY.observe(time.perf_counter() - start)
    REQUESTS.labels(status="200").inc()
    return {"ok": True, "work_ms": WORK_MS}


@app.route("/healthz")
def healthz():
    return "ok"


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
