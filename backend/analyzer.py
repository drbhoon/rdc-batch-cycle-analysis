"""
analyzer.py

Enriches raw vision_pipeline events with:
  - RMC benchmark targets and thresholds
  - Delay detection and status classification (ok / slow / critical)
  - CPM-based critical path and bottleneck ranking
  - Throughput calculation (m³/hr) current vs projected
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

# ─────────────────────────────────────────────────────────────────────────────
# RMC DOMAIN KNOWLEDGE — Benchmark targets per batch sequence step
# Source: Standard RMC plant practice (twin-shaft mixer, screw conveyor feed)
# All times in seconds.
# ─────────────────────────────────────────────────────────────────────────────
BENCHMARKS: Dict[str, Dict] = {
    "sand":             {"target_sec": 12, "critical_sec": 20, "component": "Weigh Batcher", "group": "aggregate"},
    "ca10mm":           {"target_sec": 8,  "critical_sec": 15, "component": "Stone Batcher",  "group": "aggregate"},
    "ca20mm":           {"target_sec": 10, "critical_sec": 18, "component": "Stone Batcher",  "group": "aggregate"},
    "skip_up":          {"target_sec": 15, "critical_sec": 25, "component": "Skip Hoist",     "group": "skip"},
    "skip_discharge":   {"target_sec": 10, "critical_sec": 18, "component": "Skip Tip",       "group": "skip"},
    "skip_down":        {"target_sec": 12, "critical_sec": 20, "component": "Skip Hoist",     "group": "skip"},
    "cement_feed":      {"target_sec": 30, "critical_sec": 45, "component": "Cement Screw",   "group": "binder"},
    "flyash_feed":      {"target_sec": 20, "critical_sec": 35, "component": "Flyash Screw",   "group": "binder"},
    "ulttne_feed":      {"target_sec": 5,  "critical_sec": 10, "component": "Admixture Pump", "group": "admixture"},
    "cement_discharge": {"target_sec": 20, "critical_sec": 35, "component": "Cement Silo Gate","group": "binder"},
    "water_feed":       {"target_sec": 30, "critical_sec": 45, "component": "Water Valve",    "group": "water"},
    "water_discharge":  {"target_sec": 25, "critical_sec": 40, "component": "Water Pump",     "group": "water"},
    "adx_feed":         {"target_sec": 12, "critical_sec": 22, "component": "Admixture Pump", "group": "admixture"},
    "adx_discharge":    {"target_sec": 12, "critical_sec": 22, "component": "Admixture Valve","group": "admixture"},
    "mixing_time":      {"target_sec": 45, "critical_sec": 60, "component": "Mixer",          "group": "mixing"},
    "mix_discharge":    {"target_sec": 15, "critical_sec": 25, "component": "Discharge Gate", "group": "discharge"},
    "closing_dis_gate": {"target_sec": 3,  "critical_sec": 6,  "component": "Gate Actuator",  "group": "discharge"},
}

# Steps that lie on the critical path by definition (sequential, cannot be parallelised)
# Any delay here directly extends total cycle time.
CRITICAL_PATH_STEPS = [
    "sand", "ca10mm", "ca20mm",
    "skip_up", "skip_discharge", "skip_down",
    "cement_feed", "cement_discharge",
    "water_feed", "water_discharge",
    "mixing_time", "mix_discharge", "closing_dis_gate",
]


def classify_status(actual: float, target: float, critical: float) -> str:
    """Returns 'ok', 'slow', or 'critical' based on actual vs benchmarks."""
    if actual <= target:
        return "ok"
    elif actual <= critical:
        return "slow"
    else:
        return "critical"


def annotate_events(events: List[Dict], benchmark_overrides: dict = None) -> List[Dict]:
    """
    Takes raw events list from vision_pipeline.analyze_video() and adds:
      target_sec, critical_sec, delta_sec, status, on_critical_path,
      component, group
    """
    if benchmark_overrides is None:
        benchmark_overrides = {}
        
    annotated = []
    for ev in events:
        sid = ev["id"]
        bench = BENCHMARKS.get(sid, {})
        
        target = float(benchmark_overrides.get(sid, bench.get("target_sec", ev["duration_sec"])))
        # Scale critical automatically based on the new target
        # Original logic: critical was ~1.5x to 1.8x target. Let's just do target * 1.5 if not explicitly handled, 
        # but to keep it simple, we just override target and keep critical relative to new target.
        orig_target = bench.get("target_sec", ev["duration_sec"])
        orig_critical = bench.get("critical_sec", ev["duration_sec"] * 1.5)
        ratio = orig_critical / orig_target if orig_target > 0 else 1.5
        critical = target * ratio
        
        actual = ev["duration_sec"]
        delta = round(max(0, actual - target), 2)
        status = classify_status(actual, target, critical)
        annotated.append({
            **ev,
            "target_sec":      target,
            "critical_sec":    critical,
            "delta_sec":       delta,
            "status":          status,
            "on_critical_path": sid in CRITICAL_PATH_STEPS,
            "component":       bench.get("component", "—"),
            "group":           bench.get("group", "other"),
        })
    return annotated


def compute_bottlenecks(annotated_events: List[Dict]) -> List[Dict]:
    """
    Ranks steps by time lost (delta_sec > 0), weighted by whether
    they are on the critical path.
    Returns top bottlenecks sorted by impact (most impactful first).
    """
    bottlenecks = []
    for ev in annotated_events:
        if ev["delta_sec"] > 0:
            # Critical path delays count double — they directly block cycle completion
            cp_weight = 2.0 if ev["on_critical_path"] else 1.0
            impact_score = ev["delta_sec"] * cp_weight
            bottlenecks.append({
                "id":              ev["id"],
                "name":            ev["name"],
                "actual_sec":      ev["duration_sec"],
                "target_sec":      ev["target_sec"],
                "delta_sec":       ev["delta_sec"],
                "status":          ev["status"],
                "on_critical_path": ev["on_critical_path"],
                "component":       ev["component"],
                "group":           ev["group"],
                "impact_score":    round(impact_score, 2),
            })
    bottlenecks.sort(key=lambda x: x["impact_score"], reverse=True)
    return bottlenecks


def compute_throughput(total_cycle_time_sec: float, batch_volume_m3: float, benchmark_overrides: dict = None) -> Dict:
    """
    Calculates throughput metrics.
    throughput_m3_hr = (batch_volume_m3 / total_cycle_time_sec) * 3600
    """
    if benchmark_overrides is None:
        benchmark_overrides = {}
        
    if total_cycle_time_sec <= 0:
        return {}
    current = round((batch_volume_m3 / total_cycle_time_sec) * 3600, 3)

    # Ideal: all steps exactly at target
    target_total = sum(
        float(benchmark_overrides.get(sid, BENCHMARKS.get(sid, {}).get("target_sec", 0)))
        for sid in BENCHMARKS
    )
    ideal = round((batch_volume_m3 / target_total) * 3600, 3) if target_total > 0 else current

    efficiency_pct = round((current / ideal) * 100, 1) if ideal > 0 else 100.0

    return {
        "batch_volume_m3":    batch_volume_m3,
        "total_cycle_sec":    total_cycle_time_sec,
        "current_m3_hr":      current,
        "ideal_m3_hr":        ideal,
        "efficiency_pct":     efficiency_pct,
    }


def compute_projected_throughput(
    annotated_events: List[Dict],
    bottlenecks: List[Dict],
    batch_volume_m3: float,
    fix_top_n: int = 3
) -> float:
    """
    Simulates fixing the top N bottlenecks (setting them to target)
    and returns the projected throughput in m³/hr.
    """
    to_fix = {b["id"] for b in bottlenecks[:fix_top_n]}
    projected_total = sum(
        ev["target_sec"] if ev["id"] in to_fix else ev["duration_sec"]
        for ev in annotated_events
    )
    if projected_total <= 0:
        return 0.0
    return round((batch_volume_m3 / projected_total) * 3600, 3)


def full_analysis(raw_result: Dict, batch_volume_m3: float = 0.5, benchmark_overrides: dict = None) -> Dict:
    """
    Top-level function.
    Accepts the dict from vision_pipeline.analyze_video() and returns
    a fully enriched analysis dict ready for the frontend.
    """
    events = raw_result.get("events", [])
    annotated = annotate_events(events, benchmark_overrides)
    bottlenecks = compute_bottlenecks(annotated)
    total_cycle = raw_result.get("total_cycle_time_sec", 0)

    throughput = compute_throughput(total_cycle, batch_volume_m3, benchmark_overrides)
    projected_m3_hr = compute_projected_throughput(annotated, bottlenecks, batch_volume_m3)
    throughput["projected_m3_hr"] = projected_m3_hr

    # Throughput gain if top 3 are fixed
    gain = round(projected_m3_hr - throughput["current_m3_hr"], 3)
    throughput["projected_gain_m3_hr"] = gain

    return {
        **raw_result,
        "batch_volume_m3":  batch_volume_m3,
        "events":           annotated,
        "bottlenecks":      bottlenecks,
        "throughput":       throughput,
    }
