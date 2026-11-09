"""Build a KEDA cron ScaledObject from the traffic profile, aligned to a replay start time."""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import MAX_REPLICAS, MIN_REPLICAS, NAMESPACE, DEPLOYMENT, load_profile, replicas_for  # noqa: E402


def plan_replicas(rps, lookahead):
    """Replicas per bucket, pre-warming for the highest load in the next `lookahead` buckets."""
    return [replicas_for(max(rps[i : i + lookahead + 1])) for i in range(len(rps))]


def windows(replicas):
    """Merge consecutive equal buckets into (start_idx, end_idx, replicas) runs, skipping the baseline."""
    runs, i = [], 0
    while i < len(replicas):
        j = i
        while j < len(replicas) and replicas[j] == replicas[i]:
            j += 1
        if replicas[i] > MIN_REPLICAS:
            runs.append((i, j, replicas[i]))
        i = j
    return runs


def cron(epoch):
    t = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return f"{t.minute} {t.hour} * * *"


def build_manifest(profile, start_epoch, lookahead=1):
    bucket = profile["replay_bucket_seconds"]
    runs = windows(plan_replicas(profile["rps"], lookahead))
    if not runs:
        runs = [(0, len(profile["rps"]), MIN_REPLICAS)]
    triggers = ""
    for a, b, n in runs:
        triggers += (
            "  - type: cron\n"
            "    metadata:\n"
            "      timezone: UTC\n"
            f'      start: "{cron(start_epoch + a * bucket)}"\n'
            f'      end: "{cron(start_epoch + b * bucket)}"\n'
            f'      desiredReplicas: "{n}"\n'
        )
    return (
        "apiVersion: keda.sh/v1alpha1\n"
        "kind: ScaledObject\n"
        "metadata:\n"
        "  name: demo-scheduled\n"
        f"  namespace: {NAMESPACE}\n"
        "spec:\n"
        "  scaleTargetRef:\n"
        f"    name: {DEPLOYMENT}\n"
        f"  minReplicaCount: {MIN_REPLICAS}\n"
        f"  maxReplicaCount: {MAX_REPLICAS}\n"
        "  pollingInterval: 15\n"
        "  advanced:\n"
        "    horizontalPodAutoscalerConfig:\n"
        "      behavior:\n"
        "        scaleDown:\n"
        "          stabilizationWindowSeconds: 0\n"
        "  triggers:\n" + triggers
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default=None)
    ap.add_argument("--start-epoch", type=int, required=True, help="unix time (minute-aligned) when the replay begins")
    ap.add_argument("--lookahead", type=int, default=1, help="buckets of pre-warming before a load step")
    ap.add_argument("--out", default="k8s/generated/scaledobject-scheduled.yaml")
    args = ap.parse_args()

    manifest = build_manifest(load_profile(args.profile), args.start_epoch, args.lookahead)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manifest)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
