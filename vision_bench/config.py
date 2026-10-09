"""Validated bench configuration. Rectangle coordinates refer to transformed input."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


class BenchError(ValueError):
    """An actionable error safe to show to the operator."""


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def default_config() -> dict:
    return {
        "schema_version": 1,
        "camera_index": 0,
        "mirror": False,
        "rotation": 0,
        "slots": [
            {"id": "Morning", "name": "早上", "rect": [0.04, 0.15, 0.32, 0.9]},
            {"id": "Noon", "name": "中午", "rect": [0.36, 0.15, 0.64, 0.9]},
            {"id": "Evening", "name": "晚上", "rect": [0.68, 0.15, 0.96, 0.9]},
        ],
        "detector": {
            "backend": "opencv",
            "yolo_model": "",
            "roboflow_model": "pill-detection-fnftd/3",
            "confidence": 0.4,
            "timeout_seconds": 20,
            "allowed_classes": ["pill", "pills", "tablet", "tablets", "capsule", "capsules"],
        },
        "opencv": {
            "hsv_ranges": [[[0, 0, 170], [179, 75, 255]]],
            "min_area_ratio": 0.003,
            "max_area_ratio": 0.20,
            "aspect_min": 0.30,
            "aspect_max": 3.5,
            "min_fill_ratio": 0.42,
            "max_mask_coverage": 0.75,
        },
        "quality": {"min_mean_brightness": 12, "max_overexposed_fraction": 0.85,
                    "min_laplacian_variance": 0},
    }


def _number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BenchError(f"{label} 必须是有限数值")
    if not low <= value <= high:
        raise BenchError(f"{label} 必须在 {low} 到 {high} 之间")


def validate_config(config: dict) -> dict:
    try:
        if config["schema_version"] != 1:
            raise BenchError("不支持的配置版本")
        _number(config["camera_index"], 0, 100, "camera_index")
        if not isinstance(config["camera_index"], int):
            raise BenchError("摄像头编号必须为整数")
        if not isinstance(config["mirror"], bool) or config["rotation"] not in (0, 90, 180, 270):
            raise BenchError("mirror 必须是布尔值，rotation 必须是 0/90/180/270")
        slots = config["slots"]
        if not isinstance(slots, list) or not slots:
            raise BenchError("至少设置一个识别区域")
        ids = set()
        for slot in slots:
            sid, rect = slot["id"], slot["rect"]
            if not isinstance(sid, str) or not sid or sid in ids:
                raise BenchError("格子 ID 必须是非空且不重复的字符串")
            ids.add(sid)
            if not isinstance(slot["name"], str) or not slot["name"].strip():
                raise BenchError("格子名称不能为空")
            if len(rect) != 4:
                raise BenchError("rect 必须包含四个归一化坐标")
            for coordinate in rect:
                _number(coordinate, 0, 1, "ROI 坐标")
            if rect[0] >= rect[2] or rect[1] >= rect[3]:
                raise BenchError("ROI 左上角必须位于右下角之前")
        for i, first in enumerate(slots):
            for second in slots[i + 1:]:
                a, b = first["rect"], second["rect"]
                if max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3]):
                    raise BenchError("识别区域不能重叠，否则一个药丸可能被重复计数")
        detector = config["detector"]
        if detector["backend"] not in ("opencv", "yolo", "roboflow"):
            raise BenchError("backend 必须为 opencv/yolo/roboflow")
        _number(detector["confidence"], 0, 1, "confidence")
        _number(detector["timeout_seconds"], 1, 120, "timeout_seconds")
        if not isinstance(detector["allowed_classes"], list) or not detector["allowed_classes"] or not all(isinstance(v, str) and v for v in detector["allowed_classes"]):
            raise BenchError("allowed_classes 不能为空")
        cv = config["opencv"]
        if not cv["hsv_ranges"]:
            raise BenchError("hsv_ranges 不能为空")
        for low, high in cv["hsv_ranges"]:
            if len(low) != 3 or len(high) != 3:
                raise BenchError("HSV 上下界必须各有三个整数")
            for i, limit in enumerate((179, 255, 255)):
                for v in (low[i], high[i]):
                    _number(v, 0, limit, "HSV")
                    if not isinstance(v, int):
                        raise BenchError("HSV 值必须为整数")
                if low[i] > high[i]:
                    raise BenchError("HSV 下界不能大于上界；红色跨界请拆成两个区间")
        for key in ("min_area_ratio", "max_area_ratio", "min_fill_ratio", "max_mask_coverage"):
            _number(cv[key], 0, 1, key)
        if not 0 < cv["min_area_ratio"] < cv["max_area_ratio"] <= 1:
            raise BenchError("轮廓面积上下界无效")
        _number(cv["aspect_min"], 0.01, 100, "aspect_min")
        _number(cv["aspect_max"], cv["aspect_min"], 100, "aspect_max")
        q = config["quality"]
        _number(q["min_mean_brightness"], 0, 255, "min_mean_brightness")
        _number(q["max_overexposed_fraction"], 0, 1, "max_overexposed_fraction")
        _number(q["min_laplacian_variance"], 0, 100000, "min_laplacian_variance")
        digest(config)  # Reject non-JSON values / NaN even in extra fields.
    except BenchError:
        raise
    except (KeyError, TypeError, OverflowError, ValueError) as exc:
        raise BenchError(f"配置字段缺失或格式错误：{exc}") from exc
    return config


def load_config(path: Path) -> dict:
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8-sig")))


def save_config(path: Path, config: dict):
    validate_config(config)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
