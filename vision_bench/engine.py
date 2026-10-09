"""Strict inputs and detectors; never falls back to a simulator or another model."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import PIL

from smart_pillbox_opencv import LocalYoloPillDetector, PillDetector, SlotVisionResult
from .config import BenchError, validate_config


@dataclass
class Observation:
    result: SlotVisionResult | None
    status: str
    reason: str = ""
    quality: dict | None = None


def read_image(path: Path) -> np.ndarray:
    try:
        image = cv2.imdecode(np.frombuffer(Path(path).read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    except OSError as exc:
        raise BenchError(f"不能读取图片：{Path(path).name}") from exc
    if image is None:
        raise BenchError("无法解码图片，请使用 PNG/JPEG/BMP 等有效图片")
    return image


def write_image(path: Path, image: np.ndarray):
    path = Path(path)
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise BenchError("图片编码失败")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.tobytes())


def transform_frame(raw: np.ndarray, config: dict) -> np.ndarray:
    if raw is None or not isinstance(raw, np.ndarray) or raw.ndim != 3 or raw.shape[2] != 3 or raw.dtype != np.uint8:
        raise BenchError("输入必须是有效的 uint8 BGR 图片")
    frame = raw.copy()
    rotation = config["rotation"]
    if rotation:
        flag = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_COUNTERCLOCKWISE}[rotation]
        frame = cv2.rotate(frame, flag)
    if config["mirror"]:
        frame = cv2.flip(frame, 1)
    return frame


def pixel_rect(frame, slot):
    h, w = frame.shape[:2]
    a, b, c, d = slot["rect"]
    x1, y1, x2, y2 = round(a * w), round(b * h), round(c * w), round(d * h)
    if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h) or min(x2 - x1, y2 - y1) < 10:
        raise BenchError(f"{slot['name']} 区域越界或小于10像素，请重新设置区域")
    return x1, y1, x2, y2


def make_demo_frame(config: dict):
    """Known synthetic discs, explicitly test fixtures, never real-drug evidence."""
    frame = np.full((400, 800, 3), 35, np.uint8)
    known_counts = {}
    for i, slot in enumerate(config["slots"]):
        x1, y1, x2, y2 = pixel_rect(frame, slot)
        count = (2, 1, 3)[i % 3]
        step = (x2 - x1) / (count + 1)
        radius = max(1, int(min(step * .28, (y2 - y1) * .1)))
        for j in range(count):
            center = (round(x1 + step * (j+1)), (y1+y2)//2)
            cv2.circle(frame, center, radius, (230, 230, 230), -1)
        known_counts[slot["id"]] = count
    return frame, known_counts


class CameraSource:
    def __init__(self, index=0, factory=None):
        factory = factory or cv2.VideoCapture
        self.capture = factory(index)
        self.index = index
        if not self.capture.isOpened():
            self.capture.release()
            raise BenchError(f"摄像头 {index} 无法打开；请检查编号、权限和占用情况。未切换模拟器。")

    def read(self):
        ok, raw = self.capture.read()
        if not ok or raw is None or raw.size == 0:
            self.close()
            raise BenchError("摄像头读取失败，已停止预览。请重新连接；未生成零数量或模拟帧。")
        return raw

    def close(self):
        self.capture.release()


def _sha_file(path: Path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class BenchDetector:
    def __init__(self, config: dict):
        self.config = copy.deepcopy(validate_config(config))
        self.backend = self.config["detector"]["backend"]
        self.legacy_mask = PillDetector()
        self.yolo = None
        self.identity = {
            "backend": self.backend,
            "python": sys.version.split()[0], "opencv": cv2.__version__,
            "numpy": np.__version__, "pillow": PIL.__version__,
            "bench_engine_sha256": _sha_file(Path(__file__)),
            "config_code_sha256": _sha_file(Path(__file__).with_name("config.py")),
            "legacy_detector_sha256": _sha_file(Path(__file__).resolve().parents[1] / "smart_pillbox_opencv.py"),
            "tool_code_sha256": {name: _sha_file(Path(__file__).with_name(name))
                                 for name in ("engine.py", "config.py", "data.py", "gui.py")},
            "entry_sha256": _sha_file(Path(__file__).resolve().parents[1] / "bench_tool.py"),
            "smoothing": "none", "medication_events": "disabled",
        }
        options = self.config["detector"]
        if self.backend == "opencv":
            self.identity["model"] = "HSV-contour-bench-v1"
            self.identity["confidence_kind"] = "mask-coverage-score-not-calibrated-probability"
        elif self.backend == "yolo":
            model = Path(options["yolo_model"])
            if not options["yolo_model"] or not model.is_file():
                raise BenchError("本地YOLO需要已有的专用药丸权重文件，不会下载通用权重")
            self.yolo = LocalYoloPillDetector(model, options["confidence"])
            allowed = {v.lower() for v in options["allowed_classes"]}
            self.yolo.allowed_class_names = {str(v).lower() for v in self.yolo.names.values()} & allowed
            if not self.yolo.allowed_class_names:
                raise BenchError("权重类别与药丸白名单不匹配；请提供专用模型或核实 allowed_classes")
            import ultralytics
            self.identity.update(model=model.name, weights_sha256=_sha_file(model),
                                 ultralytics=ultralytics.__version__, classes={str(k): v for k, v in self.yolo.names.items()})
            self.identity["confidence_kind"] = "model-output-not-empirical-accuracy"
        else:
            if not os.environ.get("ROBOFLOW_API_KEY"):
                raise BenchError("选择云端检测后需在环境变量中设置 ROBOFLOW_API_KEY")
            if not re.fullmatch(r"[A-Za-z0-9_-]+/\d+", options["roboflow_model"]):
                raise BenchError("Roboflow模型格式应为 project/version，如 pill-detection-fnftd/3")
            self.identity.update(model=options["roboflow_model"], endpoint="https://serverless.roboflow.com")
            self.identity["confidence_kind"] = "model-output-not-empirical-accuracy"

    def _quality(self, roi):
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        metrics = {"mean_brightness": float(gray.mean()),
                   "overexposed_fraction": float((gray >= 250).mean()),
                   "laplacian_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var())}
        q = self.config["quality"]
        if metrics["mean_brightness"] < q["min_mean_brightness"]:
            return metrics, "区域过暗，无法判断"
        if metrics["overexposed_fraction"] > q["max_overexposed_fraction"]:
            return metrics, "区域大面积过曝或白底，需人工核查"
        if q["min_laplacian_variance"] and metrics["laplacian_variance"] < q["min_laplacian_variance"]:
            return metrics, "区域可能失焦（阈值需台架标定），无法判断"
        return metrics, ""

    def _opencv(self, frame, slot, rect, quality):
        x1, y1, x2, y2 = rect
        roi = frame[y1:y2, x1:x2]
        cv = self.config["opencv"]
        ranges = [(np.array(low, dtype=np.uint8), np.array(high, dtype=np.uint8))
                  for low, high in cv["hsv_ranges"]]
        mask = self.legacy_mask.build_color_mask(cv2.cvtColor(roi, cv2.COLOR_BGR2HSV), ranges)
        coverage = cv2.countNonZero(mask) / mask.size
        quality["mask_coverage"] = coverage
        if coverage > cv["max_mask_coverage"]:
            return Observation(None, "uncertain", "颜色掩膜占比过高，背景可能被当成药片", quality)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        accepted = []
        for contour in contours:
            area = cv2.contourArea(contour)
            _, _, w, h = cv2.boundingRect(contour)
            if (mask.size * cv["min_area_ratio"] <= area <= mask.size * cv["max_area_ratio"]
                    and cv["aspect_min"] <= w / h <= cv["aspect_max"]
                    and area / (w * h) >= cv["min_fill_ratio"]):
                accepted.append(contour + np.array([[[x1, y1]]], dtype=np.int32))
        count = len(accepted)
        result = SlotVisionResult(count > 0, min(1., coverage / .075), coverage, rect, count,
                                  accepted, {"candidate_pill": count})
        return Observation(result, "ok", quality=quality)

    def _cloud(self, frame):
        # Roboflow legacy image endpoint: base64 image in body, no resized/cached input.
        # HTTP errors are deliberately stripped of URL/body (which can contain the key).
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise BenchError("云端输入编码失败")
        options = self.config["detector"]
        params = urllib.parse.urlencode({"api_key": os.environ["ROBOFLOW_API_KEY"],
                                         "confidence": options["confidence"] * 100, "overlap": 30})
        url = f"https://serverless.roboflow.com/{options['roboflow_model']}?{params}"
        request = urllib.request.Request(url, data=base64.b64encode(encoded.tobytes()),
                                         headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=options["timeout_seconds"]) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise BenchError(f"云端请求失败（HTTP {exc.code}）；未回退其他算法") from None
        except Exception:
            raise BenchError("云端请求失败、超时或响应无效；未回退其他算法") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("predictions"), list):
            raise BenchError("云端响应没有有效 predictions；无法判断")
        # Retain selected server metadata, not arbitrary response text or secrets.
        self.last_cloud_info = {k: payload[k] for k in ("inference_id", "time") if k in payload}
        return payload["predictions"]

    def detect(self, frame, manual_invalid="") -> dict[str, Observation]:
        self.last_cloud_info = {}
        slots = self.config["slots"]
        if manual_invalid:
            return {s["id"]: Observation(None, "uncertain", f"人工标记：{manual_invalid}") for s in slots}
        rects, qualities, observations = {}, {}, {}
        for slot in slots:
            sid = slot["id"]
            try:
                rect = pixel_rect(frame, slot)
                x1, y1, x2, y2 = rect
                metrics, reason = self._quality(frame[y1:y2, x1:x2])
                rects[sid], qualities[sid] = rect, metrics
                if reason:
                    observations[sid] = Observation(None, "uncertain", reason, metrics)
            except BenchError as exc:
                observations[sid] = Observation(None, "error", str(exc))
        if self.backend == "opencv":
            for slot in slots:
                if slot["id"] not in observations:
                    observations[slot["id"]] = self._opencv(frame, slot, rects[slot["id"]], qualities[slot["id"]])
            return observations
        if len(observations) == len(slots):
            return observations  # Do not upload unusable images unnecessarily.
        try:
            predictions = self.yolo._infer_frame(frame) if self.backend == "yolo" else self._cloud(frame)
            allowed = {v.lower() for v in self.config["detector"]["allowed_classes"]}
            normalized = []
            for p in predictions:
                label = str(p.get("class", "")).lower()
                if label not in allowed:
                    continue
                values = [float(p[k]) for k in ("x", "y", "width", "height", "confidence")]
                if not all(np.isfinite(v) for v in values) or values[2] <= 0 or values[3] <= 0 or not 0 <= values[4] <= 1:
                    raise BenchError("模型返回无效检测框")
                if values[4] >= self.config["detector"]["confidence"]:
                    normalized.append((label, *values))
        except Exception as exc:
            # No fallback; all otherwise usable slots explicitly fail.
            reason = str(exc) if isinstance(exc, BenchError) else f"{self.backend} 推理失败（{type(exc).__name__}）"
            for slot in slots:
                if slot["id"] not in observations:
                    observations[slot["id"]] = Observation(None, "error", reason, qualities[slot["id"]])
            return observations
        for slot in slots:
            sid = slot["id"]
            if sid in observations:
                continue
            x1, y1, x2, y2 = rects[sid]
            contours, classes, scores = [], {}, []
            for label, cx, cy, w, h, confidence in normalized:
                if x1 <= cx < x2 and y1 <= cy < y2:
                    box = np.array([[[int(cx-w/2), int(cy-h/2)]], [[int(cx+w/2), int(cy-h/2)]],
                                    [[int(cx+w/2), int(cy+h/2)]], [[int(cx-w/2), int(cy+h/2)]]], np.int32)
                    contours.append(box)
                    classes[label] = classes.get(label, 0) + 1
                    scores.append(confidence)
            count = len(contours)
            observations[sid] = Observation(SlotVisionResult(count > 0, max(scores, default=0.), 0.,
                                                            rects[sid], count, contours, classes),
                                           "ok", quality=qualities[sid])
        return observations
