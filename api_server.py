from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

import smart_pillbox_opencv as pillbox


class PeriodRequest(BaseModel):
    period: str = Field(pattern="^(Morning|Noon|Evening)$")


class SimulateTakeRequest(BaseModel):
    slot: str | None = Field(default=None, pattern="^(Morning|Noon|Evening)$")
    count: int = Field(default=0, ge=0, le=3)


class SimulateSetRequest(BaseModel):
    slot: str = Field(pattern="^(Morning|Noon|Evening)$")
    count: int = Field(ge=0, le=3)


app = FastAPI(title="Smart Pillbox API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

detector = pillbox.PillDetector()
tracker = pillbox.MedicationTracker(pillbox.SLOTS_CONFIG.keys())
slot_states = {"Morning": 1, "Noon": 1, "Evening": 1}
event_log: list[dict[str, Any]] = []


def now_label() -> str:
    return datetime.now().strftime("%H:%M:%S")


def period_label(period: str) -> str:
    return pillbox.SLOTS_CONFIG[period]["cn"]


def feedback_label(status: str, slot: str) -> str:
    labels = {
        "ready": "药量正确",
        "wrong_ready": "装药异常",
        "waiting": "取药处理中",
        "warning": "剂量异常",
        "missed": "漏服风险",
        "critical": "错误药格",
        "confirmed": "取药确认",
        "uncertain": "视觉不确定",
        "recovery": "恢复监控",
        "empty_normal": "空置就绪",
    }
    if slot != pillbox.CURRENT_PERIOD and status in {"ready", "empty_normal"}:
        return "待时段"
    return labels.get(status, status)


def event_kind(message: str) -> str:
    if "[CRITICAL]" in message:
        return "critical"
    if "[WARNING]" in message:
        return "warning"
    if "TAKE_MED_EVENT" in message:
        return "take"
    if "[REWARD]" in message:
        return "reward"
    return "info"


def remember_events(events: list[str]) -> None:
    for message in events:
        event_log.insert(
            0,
            {
                "id": f"{time.time_ns()}",
                "time": now_label(),
                "kind": event_kind(message),
                "message": message,
            },
        )
    del event_log[50:]


def build_status() -> dict[str, Any]:
    frame = pillbox.draw_simulator_scene(slot_states)
    _processed, vision_results, feedback, events = pillbox.process_frame(frame, tracker, detector)
    remember_events(events)

    slots = {}
    for key in pillbox.SLOTS_CONFIG:
        result = vision_results[key]
        fb = feedback[key]
        expected = pillbox.MEDICATION_PLAN[key]["expected_count"]
        slots[key] = {
            "key": key,
            "label": period_label(key),
            "pill_count": result.pill_count,
            "expected_count": expected,
            "confidence": round(float(result.confidence), 2),
            "present": bool(result.present),
            "status": fb.status,
            "status_label": feedback_label(fb.status, key),
            "message": fb.text,
            "class_counts": result.class_counts or {"tablets": result.pill_count},
            "is_current": key == pillbox.CURRENT_PERIOD,
        }

    completed = sum(
        1 for slot in slots.values()
        if slot["status"] == "confirmed" or slot["pill_count"] == 0
    )
    return {
        "online": True,
        "backend": "FastAPI + OpenCV simulator",
        "detector": "OpenCV fallback",
        "current_period": pillbox.CURRENT_PERIOD,
        "current_period_label": period_label(pillbox.CURRENT_PERIOD),
        "system_state": tracker.system_state,
        "led_status": tracker.led_status,
        "buzzer_status": tracker.buzzer_status,
        "voice_status": tracker.voice_status,
        "completed_count": completed,
        "total_count": 3,
        "next_reminder": {"label": period_label(pillbox.CURRENT_PERIOD), "time": "08:00"},
        "slots": slots,
        "events": event_log[:10],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    return build_status()


@app.get("/api/events")
def get_events() -> dict[str, Any]:
    return {"events": event_log[:50]}


@app.post("/api/period")
def set_period(payload: PeriodRequest) -> dict[str, Any]:
    pillbox.CURRENT_PERIOD = payload.period
    return build_status()


@app.post("/api/simulate/take")
def simulate_take(payload: SimulateTakeRequest) -> dict[str, Any]:
    slot = payload.slot or pillbox.CURRENT_PERIOD
    slot_states[slot] = payload.count
    return build_status()


@app.post("/api/simulate/set")
def simulate_set(payload: SimulateSetRequest) -> dict[str, Any]:
    slot_states[payload.slot] = payload.count
    return build_status()


@app.post("/api/reset")
def reset_demo() -> dict[str, Any]:
    global tracker
    slot_states.update({"Morning": 1, "Noon": 1, "Evening": 1})
    pillbox.CURRENT_PERIOD = "Morning"
    tracker = pillbox.MedicationTracker(pillbox.SLOTS_CONFIG.keys())
    event_log.clear()
    return build_status()


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Smart Pillbox API is running", "docs": "/docs", "status": "/api/status"}


class PlanCountsRequest(BaseModel):
    counts: dict[str, int]

    @field_validator("counts")
    @classmethod
    def validate_counts(cls, counts: dict[str, int]) -> dict[str, int]:
        if set(counts) != set(pillbox.SLOTS_CONFIG) or any(type(v) is not int or not 0 <= v <= 3 for v in counts.values()):
            raise ValueError("需要早/中/晚各格的 0-3 粒数量")
        return counts


@app.post("/api/medplan")
def set_medplan_counts(payload: PlanCountsRequest) -> dict[str, Any]:
    """Sync manually confirmed counts; does not claim to recognize medicine identity."""
    for slot, count in payload.counts.items():
        pillbox.MEDICATION_PLAN[slot]["expected_count"] = count
    remember_events(["[INFO] 家属已人工确认并同步三个药格的计划数量。"])
    return build_status()
