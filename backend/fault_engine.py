"""
fault_engine.py

RMC batching plant fault diagnosis engine.
Provides a structured fault tree per batch sequence step.
Each fault has:
  - cause: human-readable description
  - question: what to ask the operator
  - yes_action / no_action: what to tell them based on their answer
  - yes_next / no_next: id of next fault to check, or None if resolved

Uses Gemini API for open-ended / unexpected responses.
"""

import os
import uuid
from typing import Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# FAULT TREE — keyed by sequence step ID
# Each step has a list of faults in diagnostic priority order.
# ─────────────────────────────────────────────────────────────────────────────
FAULT_TREE: Dict[str, List[Dict]] = {

    "sand": [
        {
            "id": "sand_gate",
            "cause": "Weigh batcher gate not opening fully",
            "question": "Is the sand batcher gate indicator showing fully OPEN on the panel?",
            "yes_next": "sand_sensor",
            "no_action": "Check gate actuator pneumatic circuit. Verify air pressure ≥ 6 bar. Inspect gate for mechanical obstruction.",
        },
        {
            "id": "sand_sensor",
            "cause": "Load cell / weighing sensor issue",
            "question": "Is the sand weight reading on the display changing smoothly during fill?",
            "yes_next": "sand_moisture",
            "no_action": "Check load cell cable connections and calibration. Sand may be bridging in the hopper — use vibrator if available.",
        },
        {
            "id": "sand_moisture",
            "cause": "High moisture causing sand to clump and bridge",
            "question": "Is the sand visually wet or clumped (not free-flowing)?",
            "yes_action": "Reduce sand hopper fill level. Run hopper vibrator for 10 seconds. Consider reducing sand batch weight by 5% and check mix design.",
            "no_action": "Sand flow appears normal but is slow — inspect conveyor belt speed and weigh batcher calibration.",
        },
    ],

    "ca10mm": [
        {
            "id": "ca10_gate",
            "cause": "CA 10mm batcher gate fault",
            "question": "Is the CA 10mm aggregate batcher gate showing OPEN on the panel?",
            "yes_next": "ca10_bridging",
            "no_action": "Inspect CA 10mm gate cylinder. Check solenoid valve operation. Verify air supply.",
        },
        {
            "id": "ca10_bridging",
            "cause": "Stone bridging in hopper",
            "question": "Can you hear/see stone flowing freely into the batcher?",
            "yes_action": "Flow is occurring — check load cell for slow response.",
            "no_action": "Stone is bridging. Run vibrator or use a rod to clear the hopper throat. Check hopper slope angle (should be ≥ 60°).",
        },
    ],

    "ca20mm": [
        {
            "id": "ca20_gate",
            "cause": "CA 20mm batcher gate fault",
            "question": "Is the CA 20mm gate showing OPEN on the panel?",
            "yes_next": "ca20_bridging",
            "no_action": "Check CA 20mm gate actuator and solenoid. Inspect for stone jamming the gate.",
        },
        {
            "id": "ca20_bridging",
            "cause": "Large stone bridging in hopper",
            "question": "Is stone flowing freely into the batcher?",
            "yes_action": "Check load cell speed of response — may need recalibration.",
            "no_action": "Clear hopper bridge. Large aggregate (20mm) is prone to arching — consider hopper vibrator installation.",
        },
    ],

    "skip_up": [
        {
            "id": "skip_motor",
            "cause": "Skip hoist motor running at reduced speed",
            "question": "Is the skip hoist inverter/VFD showing rated output frequency (typically 50Hz)?",
            "yes_next": "skip_overload",
            "no_action": "VFD output is low. Check VFD parameters — raise speed setpoint. Inspect for VFD fault code.",
        },
        {
            "id": "skip_overload",
            "cause": "Skip overloaded — excess aggregate weight",
            "question": "Was the aggregate batch weight within normal range (not overloaded)?",
            "yes_next": "skip_rail",
            "no_action": "Skip is overloaded. Reduce aggregate batch weights. Check weigh batcher calibration for over-delivery.",
        },
        {
            "id": "skip_rail",
            "cause": "Skip rail friction or alignment issue",
            "question": "Are the skip guide rails clean and lubricated?",
            "yes_action": "Rails appear OK. Check hoist wire rope for fraying or stiff sections — may need lubrication.",
            "no_action": "Clean and grease the skip rails. Check for any debris or stone on the rail path.",
        },
    ],

    "skip_discharge": [
        {
            "id": "skip_tip_angle",
            "cause": "Skip not reaching full tip position",
            "question": "Is the skip reaching the top limit switch and fully tipping?",
            "yes_next": "skip_intake",
            "no_action": "Skip not fully tipping. Check top limit switch position. Adjust skip tip mechanism if needed.",
        },
        {
            "id": "skip_intake",
            "cause": "Mixer intake chute partially blocked",
            "question": "Is the mixer inlet chute clear of any stone/concrete build-up?",
            "yes_action": "Chute is clear — check skip discharge angle and tip speed.",
            "no_action": "Clear the mixer inlet chute. Inspect chute liner for wear. Hardened concrete build-up must be chipped away during maintenance.",
        },
    ],

    "skip_down": [
        {
            "id": "skip_return",
            "cause": "Skip return speed limited by brake or VFD",
            "question": "Does the skip return (down) speed appear the same as the up speed?",
            "yes_action": "Speeds match — timing variation is likely normal. Monitor over multiple cycles.",
            "no_action": "Return speed is slower. Check VFD deceleration/acceleration parameters for return direction. Inspect dynamic brake resistor.",
        },
    ],

    "cement_feed": [
        {
            "id": "cement_screw_speed",
            "cause": "Cement screw conveyor running below rated speed",
            "question": "Is the cement screw conveyor showing rated RPM on the panel (check inverter output)?",
            "yes_next": "cement_silo_level",
            "no_action": "Screw RPM is low. Increase screw speed setpoint on the VFD. Check for VFD fault or overload trip.",
        },
        {
            "id": "cement_silo_level",
            "cause": "Cement silo low level causing poor flow",
            "question": "Is the cement silo level indicator above 25%?",
            "yes_next": "cement_lump",
            "no_action": "Silo is low — order cement refill immediately. Low level causes poor screw feed. Check bin level sensor calibration.",
        },
        {
            "id": "cement_lump",
            "cause": "Cement lumping blocking screw intake",
            "question": "Has there been recent rain or high humidity? Are you seeing cement lumps?",
            "yes_action": "Cement moisture has caused lumping. Clear screw inlet manually (lock out first). Install silo aeration pads if not present. Store cement in sealed silo.",
            "no_action": "No lumping apparent. Check screw conveyor bearing temperature — overheating causes speed reduction. Inspect coupling.",
        },
    ],

    "flyash_feed": [
        {
            "id": "flyash_screw",
            "cause": "Flyash screw conveyor speed issue",
            "question": "Is the flyash screw conveyor running at rated speed?",
            "yes_next": "flyash_silo",
            "no_action": "Increase flyash screw speed setpoint. Check VFD for fault.",
        },
        {
            "id": "flyash_silo",
            "cause": "Flyash silo bridging (flyash is fine and prone to bridging)",
            "question": "Is flyash flowing freely into the screw — can you hear steady flow?",
            "yes_action": "Flow appears OK — check load cell response.",
            "no_action": "Flyash bridging in silo. Activate silo fluidisation pads (aeration). If unavailable, carefully rod the silo outlet.",
        },
    ],

    "ulttne_feed": [
        {
            "id": "ulttne_pump",
            "cause": "Admixture dosing pump issue",
            "question": "Is the admixture dosing pump running and showing flow on the flow meter?",
            "yes_next": "ulttne_air",
            "no_action": "Pump not running or no flow. Check pump power. Inspect admixture tank level. Prime the pump if empty.",
        },
        {
            "id": "ulttne_air",
            "cause": "Air lock in admixture line",
            "question": "Do you hear air bubbles or see inconsistent flow in the dosing line?",
            "yes_action": "Air lock present. Bleed the dosing line by opening the bleed valve briefly. Refill tank keeping suction pipe submerged.",
            "no_action": "No air lock. Check flow meter calibration and dosing setpoint.",
        },
    ],

    "cement_discharge": [
        {
            "id": "cement_gate",
            "cause": "Cement weigh hopper discharge gate not opening fully",
            "question": "Is the cement weigh hopper gate showing fully OPEN?",
            "yes_next": "cement_butterfly",
            "no_action": "Gate not opening fully. Check gate actuator and cylinder. Inspect for cement build-up blocking gate travel.",
        },
        {
            "id": "cement_butterfly",
            "cause": "Butterfly valve partially blocked by hardened cement",
            "question": "Has the cement weigh hopper been cleaned recently?",
            "yes_action": "Clean hopper. Check gate seals. Cement discharge time still high — inspect mixer for back-pressure.",
            "no_action": "Clean the cement weigh hopper — hardened cement residue on gate edges reduces opening width. Chip away any build-up during PM.",
        },
    ],

    "water_feed": [
        {
            "id": "water_valve",
            "cause": "Water valve not opening fully",
            "question": "Is the water feed valve position indicator showing 100% open?",
            "yes_next": "water_pressure",
            "no_action": "Valve not fully open. Check actuator power and position feedback. Clean valve seat if blocked by scale.",
        },
        {
            "id": "water_pressure",
            "cause": "Low water supply pressure",
            "question": "Is the water supply pressure gauge showing normal pressure (≥ 2 bar)?",
            "yes_next": "water_meter",
            "no_action": "Low water pressure. Check if water storage tank is full. Inspect pump operation. Check for leaks in supply line.",
        },
        {
            "id": "water_meter",
            "cause": "Water flow meter reading slowly (scale build-up)",
            "question": "When was the water flow meter last cleaned or calibrated?",
            "yes_action": "Meter is recent — check for any restriction in water piping (scale, partial closure of isolation valve).",
            "no_action": "Service the water flow meter — scale and mineral deposits reduce accuracy and effective flow. Descale or replace meter.",
        },
    ],

    "water_discharge": [
        {
            "id": "water_dis_valve",
            "cause": "Water discharge valve slow to operate",
            "question": "Is the water discharge valve opening immediately when commanded?",
            "yes_action": "Valve operation is OK — check if water meter is causing premature cut-off.",
            "no_action": "Valve is slow. Check actuator speed. Inspect for scale build-up on valve seat. Lubricate stem.",
        },
    ],

    "adx_feed": [
        {
            "id": "adx_pump_feed",
            "cause": "Admixture pump flow rate low",
            "question": "Is the admixture pump showing rated flow on the flow meter?",
            "yes_next": "adx_tank",
            "no_action": "Low admixture flow. Check pump speed/pressure setting. Inspect pump diaphragm or peristaltic tube for wear.",
        },
        {
            "id": "adx_tank",
            "cause": "Admixture tank level low",
            "question": "Is the admixture storage tank level above 20%?",
            "yes_action": "Tank level is OK. Check dosing line for kinks or blockage.",
            "no_action": "Refill admixture tank. Check tank level sensor. Low level causes pump cavitation.",
        },
    ],

    "adx_discharge": [
        {
            "id": "adx_valve",
            "cause": "Admixture discharge valve slow or stuck",
            "question": "Does the admixture discharge valve open fully and promptly?",
            "yes_action": "Valve OK — check if dosing control system is causing delay in discharge command.",
            "no_action": "Admixture valve is slow. Clean valve internals — admixtures can leave sticky residue. Check actuator.",
        },
    ],

    "mixing_time": [
        {
            "id": "mix_rpm",
            "cause": "Mixer running below rated RPM",
            "question": "Is the mixer motor running at rated RPM (check ammeter — should be near FLA)?",
            "yes_next": "mix_blades",
            "no_action": "Mixer RPM is low. Check mixer drive VFD parameters. Inspect motor coupling. Check for overload trip.",
        },
        {
            "id": "mix_blades",
            "cause": "Worn mixer blades increasing mixing time",
            "question": "When were the mixer blades and liner plates last inspected?",
            "yes_next": "mix_stiff",
            "no_action": "Inspect mixer blades immediately — worn blades significantly increase effective mixing time. Schedule blade replacement.",
        },
        {
            "id": "mix_stiff",
            "cause": "Mix design is too stiff (low workability) requiring longer mixing",
            "question": "Is the concrete slump noticeably lower than normal today?",
            "yes_action": "Mix is too stiff. Check water content and w/c ratio. Consider adding superplasticiser. Verify admixture dosing.",
            "no_action": "Mix design appears normal. Review mixing time setpoint — it may be set higher than needed for this grade.",
        },
    ],

    "mix_discharge": [
        {
            "id": "discharge_gate",
            "cause": "Discharge gate not opening fully or stuck",
            "question": "Is the mixer discharge gate showing fully OPEN and opening promptly?",
            "yes_next": "discharge_build",
            "no_action": "Gate not opening fully. Check gate cylinder/actuator. Concrete build-up on gate is common — chip away hardened concrete during maintenance stops.",
        },
        {
            "id": "discharge_build",
            "cause": "Concrete build-up inside mixer slowing discharge",
            "question": "When was the mixer last cleaned of concrete build-up?",
            "yes_action": "Mixer is recently cleaned. Check if transit mixer truck is in position and chute is aligned.",
            "no_action": "Clean mixer interior. Hard concrete build-up reduces mixer volume and discharge speed. Schedule a water/aggregate wash cycle.",
        },
    ],

    "closing_dis_gate": [
        {
            "id": "gate_actuator",
            "cause": "Discharge gate actuator slow to close",
            "question": "Does the gate close promptly after the close command?",
            "yes_action": "Gate operation is normal — this step duration may be within acceptable variance.",
            "no_action": "Gate is closing slowly. Check air pressure to actuator cylinder (min 6 bar). Inspect cylinder rod for bending. Lubricate pivot points.",
        },
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY SESSION STORE
# Each session tracks position in fault tree for a given step
# ─────────────────────────────────────────────────────────────────────────────
_sessions: Dict[str, Dict] = {}


def start_diagnosis(step_id: str, delta_sec: float) -> Dict:
    """
    Start a new diagnosis session for a given step.
    Returns the first question and a session_id.
    """
    faults = FAULT_TREE.get(step_id)
    if not faults:
        return {
            "session_id": None,
            "status": "no_fault_tree",
            "message": f"No fault tree defined for step '{step_id}'. Please describe the issue to the operator.",
            "resolved": True,
        }

    session_id = str(uuid.uuid4())
    _sessions[session_id] = {
        "step_id":      step_id,
        "delta_sec":    delta_sec,
        "fault_index":  0,
        "history":      [],
    }

    first_fault = faults[0]
    return {
        "session_id":  session_id,
        "step_id":     step_id,
        "fault_id":    first_fault["id"],
        "cause":       first_fault["cause"],
        "question":    first_fault["question"],
        "resolved":    False,
        "history":     [],
    }


def respond_to_diagnosis(session_id: str, answer: str) -> Dict:
    """
    Process operator's answer (yes/no/text) and return next question or resolution.
    `answer` should be 'yes', 'no', or free text (handled by Gemini fallback).
    """
    session = _sessions.get(session_id)
    if not session:
        return {"error": "Session not found. Please start a new diagnosis."}

    step_id = session["step_id"]
    fault_index = session["fault_index"]
    faults = FAULT_TREE.get(step_id, [])

    if fault_index >= len(faults):
        return {
            "session_id": session_id,
            "resolved":   True,
            "message":    "All known causes have been checked. Please consult your plant maintenance team or contact support.",
            "history":    session["history"],
        }

    current_fault = faults[fault_index]

    # Normalise answer
    answer_lower = answer.strip().lower()
    is_yes = answer_lower in ("yes", "y", "true", "1", "ok", "confirmed", "correct")
    is_no  = answer_lower in ("no", "n", "false", "0", "not", "incorrect")

    # Record in history
    session["history"].append({
        "fault_id": current_fault["id"],
        "cause":    current_fault["cause"],
        "question": current_fault["question"],
        "answer":   answer,
    })

    # Determine next step
    if is_yes:
        action = current_fault.get("yes_action")
        next_fault_id = current_fault.get("yes_next")
    elif is_no:
        action = current_fault.get("no_action")
        next_fault_id = current_fault.get("no_next")
    else:
        # Ambiguous answer — use Gemini to interpret
        return _gemini_fallback(session_id, session, current_fault, answer)

    if action:
        # Resolution found
        del _sessions[session_id]
        return {
            "session_id": session_id,
            "resolved":   True,
            "cause":      current_fault["cause"],
            "action":     action,
            "history":    session["history"],
        }

    if next_fault_id:
        # Move to named next fault
        next_index = next((i for i, f in enumerate(faults) if f["id"] == next_fault_id), None)
        if next_index is not None:
            session["fault_index"] = next_index
            next_fault = faults[next_index]
            return {
                "session_id": session_id,
                "resolved":   False,
                "fault_id":   next_fault["id"],
                "cause":      next_fault["cause"],
                "question":   next_fault["question"],
                "history":    session["history"],
            }

    # Move to next fault in list
    next_index = fault_index + 1
    if next_index < len(faults):
        session["fault_index"] = next_index
        next_fault = faults[next_index]
        return {
            "session_id": session_id,
            "resolved":   False,
            "fault_id":   next_fault["id"],
            "cause":      next_fault["cause"],
            "question":   next_fault["question"],
            "history":    session["history"],
        }

    # Exhausted all faults
    del _sessions[session_id]
    return {
        "session_id": session_id,
        "resolved":   True,
        "message":    "All standard diagnostic checks are complete. The issue may be intermittent or require specialist inspection. Please log this event for maintenance follow-up.",
        "history":    session["history"],
    }


def _gemini_fallback(session_id: str, session: Dict, current_fault: Dict, answer: str) -> Dict:
    """
    Uses Gemini to interpret an ambiguous operator response and generate
    a contextual follow-up question or resolution.
    """
    try:
        import google.generativeai as genai
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        history_text = "\n".join(
            f"Q: {h['question']}\nA: {h['answer']}" for h in session["history"]
        )

        prompt = f"""You are an expert Ready Mix Concrete (RMC) batching plant technician.
You are helping diagnose why the '{current_fault['cause']}' step in the batch cycle is running slow.

Diagnostic history so far:
{history_text}

Latest question asked: {current_fault['question']}
Operator's response: "{answer}"

Based on this response from the operator, either:
1. Provide a clear, actionable resolution (if the cause is identified), or
2. Ask one more concise follow-up diagnostic question.

Respond in JSON with exactly one of these formats:
{{"resolved": true, "action": "Clear recommended action for the operator."}}
{{"resolved": false, "question": "Next diagnostic question to ask the operator."}}"""

        response = model.generate_content(prompt)
        import json, re
        text = response.text.strip()
        # Extract JSON from response
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            if result.get("resolved"):
                del _sessions[session_id]
                return {
                    "session_id": session_id,
                    "resolved":   True,
                    "cause":      current_fault["cause"],
                    "action":     result["action"],
                    "history":    session["history"],
                    "source":     "gemini",
                }
            else:
                return {
                    "session_id": session_id,
                    "resolved":   False,
                    "fault_id":   current_fault["id"],
                    "cause":      current_fault["cause"],
                    "question":   result["question"],
                    "history":    session["history"],
                    "source":     "gemini",
                }
    except Exception as e:
        pass

    # Ultimate fallback
    return {
        "session_id": session_id,
        "resolved":   False,
        "fault_id":   current_fault["id"],
        "cause":      current_fault["cause"],
        "question":   f"Could you clarify: {current_fault['question']} (Please answer Yes or No)",
        "history":    session["history"],
    }
