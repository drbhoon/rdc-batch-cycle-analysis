from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import uvicorn
import os
import json

from capture_engine import CaptureEngine
from vision_pipeline import analyze_video
from analyzer import full_analysis, BENCHMARKS
from fault_engine import start_diagnosis, respond_to_diagnosis
from vision_pipeline import SEQUENCE

app = FastAPI(title="Batch Optimization API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

capture_engine = CaptureEngine()

# ─────────────────────────────────────────────────────────────────────────────
# Recording endpoints (existing)
# ─────────────────────────────────────────────────────────────────────────────

class RecordRequest(BaseModel):
    target_window: str = "AnyDesk"
    output_filename: str = "batch_cycle_recording.mp4"

@app.post("/api/record/start")
async def start_recording(request: RecordRequest):
    success, message = capture_engine.start_recording(
        output_path=request.output_filename,
        target_window=request.target_window
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "success", "message": message}

@app.post("/api/record/stop")
async def stop_recording():
    success, message = capture_engine.stop_recording()
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "success", "message": message, "file": capture_engine.output_filename}

@app.post("/api/launch/anydesk")
async def launch_anydesk():
    import subprocess
    possible_paths = [
        r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe",
        r"C:\Program Files\AnyDesk\AnyDesk.exe",
        os.path.expandvars(r"%ProgramFiles(x86)%\AnyDesk\AnyDesk.exe"),
        os.path.expandvars(r"%ProgramFiles%\AnyDesk\AnyDesk.exe"),
        os.path.expandvars(r"%LocalAppData%\AnyDesk\AnyDesk.exe"),
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                subprocess.Popen(path)
                return {"status": "success", "message": "AnyDesk launched.", "path": path}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    try:
        subprocess.Popen(["AnyDesk.exe"])
        return {"status": "success", "message": "AnyDesk launched via PATH."}
    except Exception:
        raise HTTPException(status_code=404, detail="AnyDesk not found.")

@app.get("/api/status")
async def get_status():
    return {
        "is_recording": capture_engine.is_recording,
        "output_filename": capture_engine.output_filename,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Basic analysis (existing — raw events only)
# ─────────────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    video_filename: str = "batch_cycle_recording.mp4"
    timeline_overrides: Optional[Dict[str, float]] = None

@app.post("/api/analyze")
async def analyze_batch_cycle(request: AnalyzeRequest):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(base_dir, request.video_filename)
    try:
        result = analyze_video(video_path, request.timeline_overrides)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# NEW: Annotated analysis — enriched with delays, bottlenecks, throughput
# ─────────────────────────────────────────────────────────────────────────────

class AnnotatedAnalyzeRequest(BaseModel):
    video_filename: str = "batch_cycle_recording.mp4"
    batch_volume_m3: float = 0.5  # user-selected: 0.5, 0.75, 1, 1.25, 1.5, 2
    timeline_overrides: Optional[Dict[str, float]] = None
    benchmark_overrides: Optional[Dict[str, float]] = None

VALID_BATCH_VOLUMES = {0.5, 0.75, 1.0, 1.25, 1.5, 2.0}

@app.post("/api/analyze/annotated")
async def analyze_annotated(request: AnnotatedAnalyzeRequest):
    """
    Full enriched analysis: raw events + delay classification + bottleneck ranking
    + throughput KPIs. This is the primary endpoint for the frontend dashboard.
    """
    if request.batch_volume_m3 not in VALID_BATCH_VOLUMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid batch volume. Choose from: {sorted(VALID_BATCH_VOLUMES)}"
        )

    base_dir = os.path.dirname(os.path.abspath(__file__))
    video_path = os.path.join(base_dir, request.video_filename)

    try:
        raw = analyze_video(video_path, request.timeline_overrides)
        result = full_analysis(
            raw, 
            batch_volume_m3=request.batch_volume_m3,
            benchmark_overrides=request.benchmark_overrides
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

# ─────────────────────────────────────────────────────────────────────────────
# NEW: Settings API
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    default_simulated = {
        "sand": 10, "ca10mm": 5, "ca20mm": 8,
        "cement_feed": 23, "flyash_feed": 17, "ulttne_feed": 2,
        "water_feed": 5, "adx_feed": 0,
        "skip_up": 13, "skip_discharge": 12, "skip_down": 15,
        "cement_discharge": 10, "water_discharge": 10, "adx_discharge": 10,
        "mixing_time": 54, "mix_discharge": 10, "closing_dis_gate": 2
    }
    steps = []
    for seq in SEQUENCE:
        sid = seq["id"]
        steps.append({
            "id": sid,
            "name": seq["name"],
            "default_simulated": default_simulated.get(sid, 10),
            "default_benchmark": BENCHMARKS.get(sid, {}).get("target_sec", 10)
        })
    return {"steps": steps}

# ─────────────────────────────────────────────────────────────────────────────
# Local Expert Timeline functionality removed
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# NEW: Fault Diagnosis — stateful interactive Q&A
# ─────────────────────────────────────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    step_id: str
    delta_sec: float

@app.post("/api/diagnose")
async def diagnose_start(request: DiagnoseRequest):
    """
    Start a new fault diagnosis session for a slow/critical batch step.
    Returns the first diagnostic question and a session_id for follow-ups.
    """
    return start_diagnosis(request.step_id, request.delta_sec)

class DiagnoseRespondRequest(BaseModel):
    session_id: str
    answer: str  # 'yes', 'no', or free text

@app.post("/api/diagnose/respond")
async def diagnose_respond(request: DiagnoseRespondRequest):
    """
    Submit an operator answer to the current diagnostic question.
    Returns the next question or a resolution action.
    """
    return respond_to_diagnosis(request.session_id, request.answer)

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
