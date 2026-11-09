"""Build docs/predictive-autoscaling.pptx from the project results."""
import argparse
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).parent))
from common import (  # noqa: E402
    CAPACITY_RPS_PER_POD, MAX_REPLICAS, MIN_REPLICAS, PRICE_PER_POD_HOUR, RESULTS, ROOT, SLO_P95_SECONDS,
    THRESHOLD_RPS_PER_POD, load_results,
)

NAVY, TEAL, ORANGE, GREY, LIGHT, WHITE = (RGBColor(0x1F, 0x2D, 0x3D), RGBColor(0x16, 0xA0, 0x85), RGBColor(0xE6, 0x7E, 0x22),
                                          RGBColor(0x7F, 0x8C, 0x8D), RGBColor(0xEC, 0xF0, 0xF1), RGBColor(0xFF, 0xFF, 0xFF))


def new_slide(prs, title, notes=""):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(1.0))
    band.fill.solid()
    band.fill.fore_color.rgb = NAVY
    band.line.fill.background()
    tf = band.text_frame
    tf.margin_left = Inches(0.6)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    r = p.add_run()
    r.text = title
    r.font.size, r.font.bold, r.font.color.rgb = Pt(30), True, WHITE
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(1.0), prs.slide_width, Inches(0.06))
    accent.fill.solid()
    accent.fill.fore_color.rgb = TEAL
    accent.line.fill.background()
    if notes:
        slide.notes_slide.notes_text_frame.text = notes
    return slide


def text_box(slide, left, top, width, height, paragraphs, size=20, color=NAVY, bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    for i, text in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(8)
        r = p.add_run()
        r.text = text
        r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, color
    return box


def bullets(slide, items, left=0.7, top=1.5, width=12, height=5.5, size=22):
    return text_box(slide, left, top, width, height, [f"\u2022  {i}" for i in items], size=size)


def card(slide, left, top, width, height, title, body, fill=LIGHT, title_color=TEAL, body_size=16):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = title_color
    shape.line.width = Pt(1.5)
    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.15)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = title
    r.font.size, r.font.bold, r.font.color.rgb = Pt(body_size + 4), True, title_color
    if body:
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = body
        r2.font.size, r2.font.color.rgb = Pt(body_size), NAVY
    return shape


def arrow(slide, x1, y1, x2, y2, color=GREY):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    conn.line.color.rgb = color
    conn.line.width = Pt(2.5)
    tail = etree.SubElement(conn.line._get_or_add_ln(), qn("a:tailEnd"))
    tail.set("type", "triangle")


def table(slide, rows, left, top, width, col_widths, row_height=0.5, size=14):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), Inches(left), Inches(top), Inches(width), Inches(row_height * len(rows)))
    tbl = shape.table
    for c, w in enumerate(col_widths):
        tbl.columns[c].width = Inches(w)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = str(value)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(size)
                    run.font.bold = r == 0
                    run.font.color.rgb = WHITE if r == 0 else NAVY
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if r == 0 else (LIGHT if r % 2 else WHITE)
    return tbl


def findings(results):
    s = {m: r["summary"] for m, r in results.items()}
    out = []
    if {"static", "reactive", "scheduled"} <= s.keys():
        saved = lambda m: 100 * (1 - s[m]["pod_minutes"] / s["static"]["pod_minutes"])
        out.append(f"Both elastic strategies cut pod-minutes by about {saved('reactive'):.0f}% (reactive) and {saved('scheduled'):.0f}% (scheduled) versus a peak-sized static fleet.")
        out.append(f"Reactive spent {s['reactive']['slo_violation_pct']}% of the run over the {SLO_P95_SECONDS * 1000:.0f} ms p95 SLO (worst p95 {s['reactive']['p95_max_s']} s): it only reacts after load has arrived.")
        out.append(f"Scheduled spent {s['scheduled']['slo_violation_pct']}% over the SLO (worst p95 {s['scheduled']['p95_max_s']} s) at similar cost, because pods were ready before the load step.")
        out.append(f"Static met the SLO ({s['static']['slo_violation_pct']}% over) but paid for {s['static']['peak_replicas']} pods around the clock.")
    return out


def build(source):
    results = load_results(source)
    if not results:
        raise SystemExit(f"no results for source '{source}'")
    out_dir = RESULTS / source
    label = "live cluster" if source == "cluster" else "simulation"
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    # 1 title
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()
    text_box(s, 0.8, 2.2, 11.7, 1.5, ["Predictive Autoscaling with Traffic Replay"], size=44, color=WHITE, bold=True)
    text_box(s, 0.8, 3.6, 11.7, 1.2, ["Record real traffic. Replay it. Tune scaling before production sees the spike."], size=24, color=RGBColor(0xBD, 0xC3, 0xC7))
    text_box(s, 0.8, 5.4, 11.7, 0.8, ["k6  \u2022  KEDA  \u2022  Prometheus  \u2022  Terraform  \u2022  Kubernetes"], size=20, color=TEAL, bold=True)
    s.notes_slide.notes_text_frame.text = "Introduce the question: can we scale before the load arrives, using what we already know about our traffic?"

    # 2 problem
    sl = new_slide(prs, "The problem: autoscaling is always a little late", "Reactive scaling needs several steps before a new pod serves traffic: metric scrape, KEDA poll, HPA decision, pod start. For a sharp spike that is tens of seconds of pain.")
    bullets(sl, [
        "Static fleets are sized for the peak and idle most of the day (wasted money).",
        "Reactive autoscalers wait for load, then need scrape + poll + start-up time (users feel it).",
        "Scaling knobs (targets, windows, schedules) are usually tuned by guessing, in production.",
        "Question: can we measure the trade-off safely, before a launch or sale?",
    ])

    # 3 idea
    sl = new_slide(prs, "The idea: record, replay, tune", "Three steps, all automated and repeatable. The same profile drives every strategy so the comparison is fair.")
    card(sl, 0.7, 1.9, 3.8, 3.4, "1. Record", "Turn an access log into a profile: requests per second for each time bucket.")
    card(sl, 4.75, 1.9, 3.8, 3.4, "2. Replay", "k6 replays the profile at compressed time against a test cluster.", title_color=ORANGE)
    card(sl, 8.8, 1.9, 3.8, 3.4, "3. Tune", "Compare static, reactive and scheduled scaling on cost and latency; keep the winner.")
    text_box(sl, 0.7, 5.8, 12, 1, ["One recorded day replays in 24 minutes (1 minute = 1 hour)."], size=20, color=GREY, align=PP_ALIGN.CENTER)

    # 4 architecture
    sl = new_slide(prs, "Architecture", "Top row is offline preparation. The middle row is the live loop: k6 sends load, Prometheus measures it, KEDA scales the app. Terraform builds everything underneath.")
    card(sl, 0.5, 1.4, 2.4, 0.9, "Access log", "", body_size=14)
    card(sl, 3.5, 1.4, 2.6, 0.9, "record_traffic.py", "", body_size=14)
    card(sl, 6.7, 1.4, 2.4, 0.9, "profile.json", "", body_size=14)
    card(sl, 9.7, 1.4, 3.1, 0.9, "generate_schedule.py", "", body_size=14)
    for x1, x2 in ((2.9, 3.5), (6.1, 6.7), (9.1, 9.7)):
        arrow(sl, x1, 1.85, x2, 1.85)
    card(sl, 0.5, 3.4, 2.9, 1.0, "k6 Job", "arrival-rate replay", title_color=ORANGE, body_size=13)
    card(sl, 4.6, 3.4, 3.0, 1.0, "demo-app pods", "Flask, 20 ms CPU/request", title_color=ORANGE, body_size=13)
    card(sl, 9.5, 3.4, 3.3, 1.0, "KEDA ScaledObject", "prometheus | cron triggers", title_color=ORANGE, body_size=13)
    arrow(sl, 7.9, 2.3, 1.95, 3.4)
    arrow(sl, 3.4, 3.9, 4.6, 3.9)
    arrow(sl, 9.5, 3.9, 7.6, 3.9)
    arrow(sl, 11.25, 2.3, 11.15, 3.4)
    card(sl, 4.6, 5.0, 3.0, 0.9, "Prometheus", "", body_size=14)
    arrow(sl, 6.1, 4.4, 6.1, 5.0)
    arrow(sl, 7.6, 5.3, 10.2, 4.4)
    text_box(sl, 3.4, 4.35, 1.4, 0.4, ["traffic"], size=11, color=GREY)
    text_box(sl, 6.2, 4.55, 1.2, 0.4, ["scrape"], size=11, color=GREY)
    text_box(sl, 8.0, 3.45, 1.4, 0.4, ["scale"], size=11, color=GREY)
    bar = card(sl, 0.5, 6.2, 12.3, 0.8, "Terraform: kind cluster + KEDA + kube-prometheus-stack + image load", "", fill=NAVY, title_color=TEAL, body_size=14)
    bar.text_frame.paragraphs[0].runs[0].font.color.rgb = WHITE

    # 5 tools
    sl = new_slide(prs, "Who does what", "Each tool has exactly one job. Replace any of them (Locust for k6, Datadog for Prometheus) and the idea still holds.")
    table(sl, [
        ["Tool", "Role in this project"],
        ["k6", "Replays the recorded profile as an open-loop arrival rate"],
        ["Prometheus", "Measures request rate and p95 latency from the app's /metrics"],
        ["KEDA", "Scales the Deployment from a Prometheus query (reactive) or cron windows (scheduled)"],
        ["Terraform", "Creates the kind cluster, installs KEDA and Prometheus, loads images"],
        ["Kubernetes", "Runs the app, HPA, and the k6 Job"],
    ], 0.7, 1.6, 12, [2.4, 9.6], row_height=0.75, size=18)

    # 6 profile
    sl = new_slide(prs, "The recorded traffic", "Quiet night, a broad afternoon hump, then an evening flash-sale spike that jumps from about 55 to 90 rps within one bucket. That jump is the hard part.")
    sl.shapes.add_picture(str(out_dir / "profile.png"), Inches(0.8), Inches(1.4), width=Inches(8.4))
    bullets(sl, [
        "24 buckets, 1 bucket = 1 recorded hour = 1 minute of replay",
        "Evening spike is a step change",
        "Peak scaled to 90 rps for the lab",
    ], left=9.4, top=1.7, width=3.6, size=18)

    # 7 strategies
    sl = new_slide(prs, "Three strategies, same traffic", "Scheduled is the 'predictive' one: it uses the profile to look one bucket ahead and pre-warm pods before a step up.")
    table(sl, [
        ["", "Static", "Reactive", "Scheduled (predictive)"],
        ["How", "Fixed pods sized for peak", "KEDA watches Prometheus rps", "KEDA cron windows from the profile"],
        ["Target", f"{results['static']['summary']['peak_replicas'] if 'static' in results else '-'} pods always", f"{THRESHOLD_RPS_PER_POD} rps per pod", f"{THRESHOLD_RPS_PER_POD} rps per pod, 1 bucket look-ahead"],
        ["Strength", "Simple, safe", "No forecast needed", "Pods ready before the spike"],
        ["Weakness", "Pays for idle capacity", "Late by scrape + poll + start-up", "Needs a repeatable pattern"],
    ], 0.5, 1.6, 12.3, [1.6, 3.2, 3.6, 3.9], row_height=0.9, size=16)
    text_box(sl, 0.5, 6.4, 12.3, 0.6, [f"Pod: 20 ms CPU/request, 500m CPU limit, about {CAPACITY_RPS_PER_POD} rps capacity. Pods bounded {MIN_REPLICAS} to {MAX_REPLICAS}."], size=14, color=GREY)

    # 8 method
    sl = new_slide(prs, "How the experiment is run", "Fairness: identical profile, identical pod size, identical SLO. Cost is a proxy: pod-minutes times an illustrative price.")
    bullets(sl, [
        "run_experiment.py resets the cluster, then runs each mode in turn",
        "Scheduled mode: the cron ScaledObject is generated for that run's exact start time",
        "k6 waits for a shared start timestamp so cron windows line up with traffic",
        "Metrics pulled from Prometheus every 15 s: rps, p95, pods",
        f"SLO: p95 under {SLO_P95_SECONDS * 1000:.0f} ms. Cost: pods x minutes x ${PRICE_PER_POD_HOUR}/pod-hour",
    ], size=21)

    # 9 timeline
    sl = new_slide(prs, f"Results: timeline ({label})", "Read top to bottom: load, pods, latency. Reactive pods trail the load, and the latency peaks sit exactly at the steps. Scheduled pods step up one bucket early.")
    sl.shapes.add_picture(str(out_dir / "timeline.png"), Inches(2.6), Inches(1.2), height=Inches(6.2))

    # 10 comparison
    sl = new_slide(prs, f"Results: cost vs latency ({label})", "Static is the safe-but-expensive baseline. The interesting comparison is reactive versus scheduled: nearly identical cost, very different SLO behaviour.")
    sl.shapes.add_picture(str(out_dir / "comparison.png"), Inches(0.5), Inches(1.3), width=Inches(7.4))
    rows = [["Strategy", "Pod-min", "Over SLO", "Worst p95"]]
    for mode, r in results.items():
        x = r["summary"]
        rows.append([mode, x["pod_minutes"], f"{x['slo_violation_pct']}%", f"{x['p95_max_s']} s"])
    table(sl, rows, 8.2, 1.6, 4.8, [1.5, 1.1, 1.1, 1.1], row_height=0.6, size=14)
    text_box(sl, 0.7, 5.2, 12, 1.8, findings(results)[1:3], size=20)

    # 11 findings
    sl = new_slide(prs, "Key findings", "Numbers are derived from the results files, so they update when you re-run on a real cluster.")
    bullets(sl, findings(results), size=20)

    # 12 how to run
    sl = new_slide(prs, "Run it yourself", "Simulation needs only Python. The cluster path needs Docker, kind, Terraform and kubectl.")
    code = text_box(sl, 0.7, 1.4, 12, 5.5, [
        "# no cluster needed",
        "python scripts/simulate.py",
        "python scripts/report.py --source simulation",
        "",
        "# full lab on kind",
        "cd terraform; terraform init; terraform apply",
        "kind export kubeconfig --name autoscale-lab",
        "python scripts/run_experiment.py",
        "python scripts/report.py --source cluster",
        "python scripts/build_deck.py --source cluster",
    ], size=20)
    for p in code.text_frame.paragraphs:
        for r in p.runs:
            r.font.name = "Consolas"

    # 13 limits
    sl = new_slide(prs, "Limits and next steps", "Be upfront: the simulator and the lab prove the method, not your production numbers. Use real logs and your own SLO.")
    bullets(sl, [
        "Scheduled scaling only helps if traffic repeats; add a fallback reactive trigger for surprises",
        "Lab app is CPU-bound by design; real services also depend on databases and caches",
        "Cron granularity is one minute, so replay buckets are at least 60 s",
        "Next: forecast the schedule from history, add Grafana dashboards, run in CI before big launches",
    ], size=21)

    # 14 close
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()
    text_box(s, 0.8, 2.8, 11.7, 1.5, ["Questions?"], size=48, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    text_box(s, 0.8, 4.2, 11.7, 1, ["Measure scaling before production does it for you."], size=22, color=TEAL, align=PP_ALIGN.CENTER)

    target = ROOT / "docs" / "predictive-autoscaling.pptx"
    target.parent.mkdir(exist_ok=True)
    prs.save(target)
    print(f"wrote {target} ({len(prs.slides)} slides, data source: {source})")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=["simulation", "cluster"], default="simulation")
    args = ap.parse_args()
    build(args.source)


if __name__ == "__main__":
    main()
