"""
vision_pipeline.py

Reads a batch cycle MP4 recording and extracts event timelines by analyzing
Regions of Interest (ROIs) on the screen for color/brightness state changes.

Two modes:
  - ROI mode: uses defined screen regions to detect active states
  - Demo mode: generates a plausible timeline from the video's total duration
    (useful for testing the chart rendering before ROIs are tuned)
"""

import cv2
import numpy as np
import os
import json

# ─────────────────────────────────────────────────────────────────
# SEQUENCE DEFINITION
# Edit this list to match the actual order shown in your batching software.
# ─────────────────────────────────────────────────────────────────
SEQUENCE = [
    {"id": "sand",             "name": "SAND",                "color": "#4ade80"},  # green
    {"id": "ca10mm",           "name": "CA10MM",              "color": "#facc15"},  # yellow
    {"id": "ca20mm",           "name": "CA20MM",              "color": "#facc15"},
    {"id": "skip_up",          "name": "Skip up",             "color": "#60a5fa"},  # blue
    {"id": "skip_discharge",   "name": "Skip discharge",      "color": "#60a5fa"},
    {"id": "skip_down",        "name": "Skip Down",           "color": "#60a5fa"},
    {"id": "cement_feed",      "name": "Cement Feed",         "color": "#4ade80"},
    {"id": "flyash_feed",      "name": "Flyash Feed",         "color": "#4ade80"},
    {"id": "ulttne_feed",      "name": "ULTTNE Feed",         "color": "#f97316"},  # orange
    {"id": "cement_discharge", "name": "Cement Discharge",    "color": "#4ade80"},
    {"id": "water_feed",       "name": "Water Feed",          "color": "#60a5fa"},
    {"id": "water_discharge",  "name": "Water Discharge",     "color": "#60a5fa"},
    {"id": "adx_feed",         "name": "Adx.Feed",            "color": "#f97316"},
    {"id": "adx_discharge",    "name": "Adx Discharge",       "color": "#f97316"},
    {"id": "mixing_time",      "name": "Mixing Time",         "color": "#a78bfa"},  # purple
    {"id": "mix_discharge",    "name": "Mix Discharge",       "color": "#a78bfa"},
    {"id": "closing_dis_gate", "name": "Closing Dis.gate",    "color": "#94a3b8"},  # slate
]

# ─────────────────────────────────────────────────────────────────
# ROI DEFINITIONS (optional — leave empty list [] to use demo mode)
# Each entry: { "sequence_id": "...", "roi": (x, y, w, h),
#              "active_color_hsv_lower": [...], "active_color_hsv_upper": [...],
#              "threshold_pct": 0.3 }
# Set threshold_pct = fraction of ROI pixels that must match color to be "active".
# ─────────────────────────────────────────────────────────────────
ROI_DEFINITIONS = []  # ← Populate these after inspecting your batch software UI


def _generate_demo_timeline(video_duration_sec: float, timeline_overrides: dict = None) -> list:
    """
    Generates a timeline based on BCA guidelines, with optional user overrides.
    """
    if timeline_overrides is None:
        timeline_overrides = {}

    def get_dur(sid, default):
        return float(timeline_overrides.get(sid, default))

    events = []

    def add_event(sid, name, color, start, duration):
        events.append({
            "id": sid,
            "name": name,
            "color": color,
            "start_sec": float(start),
            "duration_sec": float(duration),
            "end_sec": float(start + duration),
            "source": "demo_custom"
        })

    # Find colors from SEQUENCE
    colors = {s["id"]: s["color"] for s in SEQUENCE}
    
    # Get durations
    d_sand = get_dur("sand", 10)
    d_ca10 = get_dur("ca10mm", 5)
    d_ca20 = get_dur("ca20mm", 8)
    d_cemf = get_dur("cement_feed", 23)
    d_flyf = get_dur("flyash_feed", 17)
    d_ultf = get_dur("ulttne_feed", 2)
    d_watf = get_dur("water_feed", 5)
    d_adxf = get_dur("adx_feed", 0)
    
    d_skipu = get_dur("skip_up", 13)
    d_skipd = get_dur("skip_discharge", 12)
    d_skipdo = get_dur("skip_down", 15)
    
    d_cemd = get_dur("cement_discharge", 10)
    d_watd = get_dur("water_discharge", 10)
    d_adxd = get_dur("adx_discharge", 10)
    
    d_mixt = get_dur("mixing_time", 54)
    d_mixd = get_dur("mix_discharge", 10)
    d_gate = get_dur("closing_dis_gate", 2)

    # 1. Feeds starting at zero
    add_event("sand", "SAND", colors.get("sand"), 0, d_sand)
    add_event("ca10mm", "CA10MM", colors.get("ca10mm"), 0, d_ca10)
    add_event("ca20mm", "CA20MM", colors.get("ca20mm"), 0, d_ca20)
    
    add_event("cement_feed", "Cement Feed", colors.get("cement_feed"), 0, d_cemf)
    add_event("flyash_feed", "Flyash Feed", colors.get("flyash_feed"), 0, d_flyf)
    add_event("ulttne_feed", "ULTTNE Feed", colors.get("ulttne_feed"), 0, d_ultf)
    
    add_event("water_feed", "Water Feed", colors.get("water_feed"), 0, d_watf)
    add_event("adx_feed", "Adx.Feed", colors.get("adx_feed"), 0, d_adxf)

    # 2. Skip operations
    skip_up_start = max(d_sand, d_ca10, d_ca20)  # After aggregates
    add_event("skip_up", "Skip up", colors.get("skip_up"), skip_up_start, d_skipu)
    
    skip_dis_start = skip_up_start + d_skipu
    add_event("skip_discharge", "Skip discharge", colors.get("skip_discharge"), skip_dis_start, d_skipd)
    add_event("skip_down", "Skip Down", colors.get("skip_down"), skip_dis_start + d_skipd, d_skipdo)

    # 3. Discharges (Cement & Skip together)
    add_event("cement_discharge", "Cement Discharge", colors.get("cement_discharge"), skip_dis_start, d_cemd)
    
    # Water & Admix discharge after 5 seconds of water feed starting
    wat_adx_dis_start = d_watf  # usually starts after water feed completes or similar. Let's stick to d_watf as it mirrors the original max(5) logic roughly, or simply wait for water feed to finish
    add_event("water_discharge", "Water Discharge", colors.get("water_discharge"), wat_adx_dis_start, d_watd)
    add_event("adx_discharge", "Adx Discharge", colors.get("adx_discharge"), wat_adx_dis_start, d_adxd)

    # 4. Mixing Time (After last discharge)
    last_discharge_end = max(
        skip_dis_start + d_skipd,
        skip_dis_start + d_cemd,
        wat_adx_dis_start + d_watd,
        wat_adx_dis_start + d_adxd
    )
    
    add_event("mixing_time", "Mixing Time", colors.get("mixing_time"), last_discharge_end, d_mixt)
    
    # 5. Mix Discharge & Gate
    mix_dis_start = last_discharge_end + d_mixt
    add_event("mix_discharge", "Mix Discharge", colors.get("mix_discharge"), mix_dis_start, d_mixd)
    add_event("closing_dis_gate", "Closing Dis.gate", colors.get("closing_dis_gate"), mix_dis_start + d_mixd, d_gate)

    # Sort events by start_sec for neatness
    events.sort(key=lambda x: x["start_sec"])
    return events


def _detect_events_from_rois(cap, fps: float, total_frames: int) -> list:
    """
    Frame-by-frame ROI analysis. Scans every Nth frame for efficiency.
    Returns a list of events with {id, name, start_sec, duration_sec, end_sec}.
    """
    SAMPLE_EVERY_N = max(1, int(fps // 2))  # sample ~2 per second
    
    # Initialize state tracking per sequence_id
    states = {r["sequence_id"]: {"active": False, "start_frame": None} for r in ROI_DEFINITIONS}
    events_raw = {r["sequence_id"]: [] for r in ROI_DEFINITIONS}
    
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_idx % SAMPLE_EVERY_N == 0:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            
            for roi_def in ROI_DEFINITIONS:
                sid = roi_def["sequence_id"]
                x, y, w, h = roi_def["roi"]
                roi_region = hsv[y:y+h, x:x+w]
                
                lower = np.array(roi_def["active_color_hsv_lower"])
                upper = np.array(roi_def["active_color_hsv_upper"])
                mask = cv2.inRange(roi_region, lower, upper)
                
                match_pct = np.count_nonzero(mask) / (w * h)
                is_active = match_pct >= roi_def.get("threshold_pct", 0.3)
                
                prev_active = states[sid]["active"]
                if is_active and not prev_active:
                    # State transition: idle -> active
                    states[sid]["active"] = True
                    states[sid]["start_frame"] = frame_idx
                elif not is_active and prev_active:
                    # State transition: active -> idle
                    start_f = states[sid]["start_frame"]
                    events_raw[sid].append({
                        "start_sec": round(start_f / fps, 2),
                        "end_sec": round(frame_idx / fps, 2),
                    })
                    states[sid]["active"] = False
                    states[sid]["start_frame"] = None
        
        frame_idx += 1
    
    # Close any events still open at end of video
    for sid, state in states.items():
        if state["active"]:
            start_f = state["start_frame"]
            events_raw[sid].append({
                "start_sec": round(start_f / fps, 2),
                "end_sec": round(total_frames / fps, 2),
            })
    
    # Build final event list in SEQUENCE order
    events = []
    for seq in SEQUENCE:
        sid = seq["id"]
        if sid not in events_raw or not events_raw[sid]:
            continue
        # For simplicity, take the longest detected event per step
        best = max(events_raw[sid], key=lambda e: e["end_sec"] - e["start_sec"])
        dur = round(best["end_sec"] - best["start_sec"], 2)
        events.append({
            "id": sid,
            "name": seq["name"],
            "color": seq["color"],
            "start_sec": best["start_sec"],
            "duration_sec": dur,
            "end_sec": best["end_sec"],
            "source": "cv_roi"
        })
    
    return events


def analyze_video(video_path: str, timeline_overrides: dict = None) -> dict:
    """
    Main entry point. Reads the video at video_path and returns a structured
    batch cycle analysis dict ready to be sent to the frontend.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 5.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_duration_sec = total_frames / fps
    
    use_demo = len(ROI_DEFINITIONS) == 0
    
    if use_demo:
        events = _generate_demo_timeline(video_duration_sec, timeline_overrides)
        cap.release()
    else:
        events = _detect_events_from_rois(cap, fps, total_frames)
        cap.release()
    
    # ── summary stats ──
    total_cycle_time = round(
        max((e["end_sec"] for e in events), default=0), 2
    )
    
    return {
        "batch_id": os.path.basename(video_path),
        "video_duration_sec": round(video_duration_sec, 2),
        "total_cycle_time_sec": total_cycle_time,
        "analysis_mode": "demo" if use_demo else "cv_roi",
        "events": events,
    }


if __name__ == "__main__":
    # Quick local test
    result = analyze_video("batch_cycle_recording.mp4")
    print(json.dumps(result, indent=2))
