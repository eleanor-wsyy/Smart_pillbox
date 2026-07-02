import argparse
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 阿尔茨海默症长者“记忆回音药盒”视觉识别原型 V4.0
# ==========================================
# 信号链：
# 1. PillDetector 视觉类：提取固定药盒 ROI 中药丸的颜色特征和数量（为接入 YOLO/FOMO 深度学习解耦）。
# 2. MedicationTracker 业务逻辑类：集成取药事件生成、时段正确性拦截（防错药）、处方剂量校验。
# 3. Pillow 图像高级渲染：抗锯齿中文微软雅黑字体，半透明圆角玻璃态信息卡片，LED 发光光晕呼吸灯。
#
# 交互测试快捷键说明：
# - 按 r/g/b 键：循环设置模拟器“早上/中午/晚上”药格内的药丸数量 (0 -> 1 -> 2 -> 3 -> 0)
# - 按 t 键：循环切换当前系统服药时间段 (Morning -> Noon -> Evening -> Morning)
# - 按空格键：模拟当前时段药格被取空
# - 按 q 键：退出程序

COLOR_RANGES = {
    "Morning": [
        (np.array([0, 100, 90]), np.array([10, 255, 255])),
        (np.array([170, 100, 90]), np.array([180, 255, 255])),
        # 白色/米色药丸：收紧低饱和度、高明度范围，降低浅色背景误检
        (np.array([0, 0, 170]), np.array([180, 55, 255])),
    ],
    "Noon": [
        (np.array([35, 70, 70]), np.array([85, 255, 255])),
        # 白色/米色药丸：收紧低饱和度、高明度范围，降低浅色背景误检
        (np.array([0, 0, 170]), np.array([180, 55, 255])),
    ],
    "Evening": [
        (np.array([90, 70, 70]), np.array([130, 255, 255])),
        # 白色/米色药丸：收紧低饱和度、高明度范围，降低浅色背景误检
        (np.array([0, 0, 170]), np.array([180, 55, 255])),
    ],
}

SLOTS_CONFIG = {
    "Morning": {
        "name": "Morning",
        "cn": "早上",
        "marker": "red",
        "center_ratio": (0.22, 0.58),
        "color": (0, 0, 255),
    },
    "Noon": {
        "name": "Noon",
        "cn": "中午",
        "marker": "green",
        "center_ratio": (0.50, 0.58),
        "color": (0, 210, 0),
    },
    "Evening": {
        "name": "Evening",
        "cn": "晚上",
        "marker": "blue",
        "center_ratio": (0.78, 0.58),
        "color": (255, 90, 0),
    },
}

WINDOW_NAME = "Memory Echo Pillbox - Vision Prototype V4.0"
PRESENT_RATIO_THRESHOLD = 0.075
MISSED_REMINDER_DELAY = 12.0
DETECTION_CONFIDENCE_THRESHOLD = 0.28
RECOVERY_DISPLAY_SECONDS = 2.5
MIN_CONTOUR_AREA_RATIO = 0.02
PILL_COUNT_EMA_ALPHA = 0.85
TAKE_EVENT_CONFIRM_FRAMES = 2

# V3.0：当前服药时间段上下文全局变量
CURRENT_PERIOD = "Morning"

# V3.0：处方用量全局配置
MEDICATION_PLAN = {
    "Morning": {"expected_count": 2},  # 早上 2 粒
    "Noon": {"expected_count": 1},     # 中午 1 粒
    "Evening": {"expected_count": 3}   # 晚上 3 粒
}


@dataclass
class SlotVisionResult:
    present: bool
    confidence: float
    color_ratio: float
    roi: tuple[int, int, int, int]
    pill_count: int
    contours: list[np.ndarray] = field(default_factory=list)
    class_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class SlotFeedback:
    status: str
    text: str
    color: tuple[int, int, int]


# ==========================================
# PIL 高清中文字体与图形辅助模块
# ==========================================
def get_font(size, bold=False):
    """自动检索 Windows 系统自带的优秀中文黑体字体，如微软雅黑，失败则使用系统默认字体"""
    font_paths = [
        "C:\\Windows\\Fonts\\msyh.ttc",     # 微软雅黑
        "C:\\Windows\\Fonts\\msyhl.ttc",    # 微软雅黑 Light
        "C:\\Windows\\Fonts\\simhei.ttf",    # 黑体
        "C:\\Windows\\Fonts\\simsun.ttc",    # 宋体
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()


def draw_badge(draw, text, rect, bg_color, text_color, font):
    """绘制圆角状态徽章并在中央填充文字"""
    draw.rounded_rectangle(rect, radius=5, fill=bg_color)
    x1, y1, x2, y2 = rect
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        offset_x = bbox[0]
        offset_y = bbox[1]
    except AttributeError:
        tw, th = draw.textsize(text, font=font)
        offset_x = 0
        offset_y = 0

    tx = x1 + (x2 - x1 - tw) // 2 - offset_x
    ty = y1 + (y2 - y1 - th) // 2 - offset_y
    draw.text((tx, ty), text, font=font, fill=text_color)


def draw_glow_led(draw, cx, cy, r, color_core, color_glow1, color_glow2):
    """绘制带双层半透明光晕效果的 LED 灯"""
    draw.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], fill=color_glow2)
    draw.ellipse([cx - r - 3, cy - r - 3, cx + r + 3, cy + r + 3], fill=color_glow1)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color_core)


class PillDetector:
    """视觉识别检测类：将传统图像算法封装，便于后续接入 YOLO 或 FOMO 深度学习检测器"""
    def __init__(self):
        self.color_ranges = COLOR_RANGES

    def detect_all(self, frame) -> dict[str, SlotVisionResult]:
        return {key: self.detect(frame, key) for key in SLOTS_CONFIG}

    def build_color_mask(self, hsv_roi, color_ranges):
        mask = np.zeros(hsv_roi.shape[:2], dtype=np.uint8)
        for lower, upper in color_ranges:
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv_roi, lower, upper))

        mask = cv2.GaussianBlur(mask, (9, 9), 0)
        _, mask = cv2.threshold(mask, 80, 255, cv2.THRESH_BINARY)

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        return mask

    def detect(self, frame, slot_key) -> SlotVisionResult:
        config = SLOTS_CONFIG[slot_key]
        x1, y1, x2, y2, cx, cy, radius = slot_geometry(frame.shape, config)
        roi = frame[y1:y2, x1:x2]
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = self.build_color_mask(hsv_roi, self.color_ranges[slot_key])

        circle_mask = np.zeros(mask.shape, dtype=np.uint8)
        cv2.circle(circle_mask, (cx - x1, cy - y1), radius - 2, 255, -1)
        soft_circle_mask = cv2.GaussianBlur(circle_mask, (11, 11), 0)
        _, soft_circle_mask = cv2.threshold(soft_circle_mask, 32, 255, cv2.THRESH_BINARY)
        mask = cv2.bitwise_and(mask, soft_circle_mask)

        colored_pixels = cv2.countNonZero(mask)
        total_pixels = max(1, cv2.countNonZero(soft_circle_mask))
        color_ratio = colored_pixels / total_pixels

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = total_pixels * MIN_CONTOUR_AREA_RATIO
        valid_contours = [
            c for c in contours
            if cv2.contourArea(c) > min_area and self._contour_is_pill_like(c)
        ]

        pill_count = len(valid_contours)
        present = pill_count > 0
        confidence = min(1.0, color_ratio / PRESENT_RATIO_THRESHOLD)

        return SlotVisionResult(
            present=present,
            confidence=confidence,
            color_ratio=color_ratio,
            roi=(x1, y1, x2, y2),
            pill_count=pill_count,
            contours=offset_contours(valid_contours, x1, y1),
        )

    @staticmethod
    def _contour_is_pill_like(contour):
        area = cv2.contourArea(contour)
        if area <= 0:
            return False

        x, y, w, h = cv2.boundingRect(contour)
        if w <= 0 or h <= 0:
            return False

        aspect_ratio = w / h
        fill_ratio = area / max(1, w * h)
        return 0.45 <= aspect_ratio <= 2.2 and fill_ratio >= 0.42


class RoboflowPillDetector:
    """Roboflow hosted YOLOv11 pill-detection-fnftd/3 适配器。

    该模型一次返回每粒药的框和类别（capsules/tablets），这里再按药格 ROI 汇总成
    业务层需要的 SlotVisionResult，避免主流程关心底层是 OpenCV 还是云端 YOLO。
    """
    MODEL_ID = "pill-detection-fnftd/3"
    MODEL_CLASSES = {"capsules", "tablets"}

    def __init__(
        self,
        api_key,
        confidence=0.4,
        overlap=0.3,
        api_url="https://serverless.roboflow.com",
        min_interval=0.6,
        timeout=8.0,
    ):
        if not api_key:
            raise ValueError("使用 Roboflow 检测器需要设置 ROBOFLOW_API_KEY 或传入 --roboflow-api-key")

        try:
            from inference_sdk import InferenceHTTPClient
        except ImportError as exc:
            raise RuntimeError("使用 Roboflow 检测器需要安装 inference-sdk：pip install inference-sdk") from exc

        self.api_key = api_key
        self.confidence = confidence
        self.overlap = overlap
        self.api_url = api_url.rstrip("/")
        self.min_interval = max(0.0, min_interval)
        self.timeout = timeout
        self.client = InferenceHTTPClient(api_url=self.api_url, api_key=self.api_key)
        self.fallback_detector = PillDetector()
        self.last_request_time = 0.0
        self.cached_predictions = []
        self.last_error = None

    def detect_all(self, frame) -> dict[str, SlotVisionResult]:
        predictions = self._infer_frame(frame)
        if predictions is None:
            return self.fallback_detector.detect_all(frame)
        return {
            key: self._build_slot_result(frame, key, predictions)
            for key in SLOTS_CONFIG
        }

    def detect(self, frame, slot_key) -> SlotVisionResult:
        return self.detect_all(frame)[slot_key]

    def _infer_frame(self, frame):
        now = time.monotonic()
        if self.cached_predictions and now - self.last_request_time < self.min_interval:
            return self.cached_predictions

        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            self.last_error = "无法将当前帧编码为 JPEG"
            return None

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(encoded.tobytes())

            payload = self.client.infer(temp_path, model_id=self.MODEL_ID)
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[WARNING] Roboflow 推理失败，已回退到本地 OpenCV 检测：{self.last_error}")
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        predictions = payload.get("predictions", [])
        self.cached_predictions = [
            p for p in predictions
            if str(p.get("class", "")).lower() in self.MODEL_CLASSES
            and float(p.get("confidence", 0.0)) >= self.confidence
        ]
        self.last_request_time = now
        self.last_error = None
        return self.cached_predictions

    def _build_slot_result(self, frame, slot_key, predictions):
        config = SLOTS_CONFIG[slot_key]
        x1, y1, x2, y2, cx, cy, radius = slot_geometry(frame.shape, config)
        slot_area = max(1, np.pi * radius * radius)

        contours = []
        class_counts = {}
        confidences = []
        detected_area = 0.0

        for pred in predictions:
            px = float(pred.get("x", 0.0))
            py = float(pred.get("y", 0.0))
            if (px - cx) ** 2 + (py - cy) ** 2 > radius ** 2:
                continue

            width = float(pred.get("width", 0.0))
            height = float(pred.get("height", 0.0))
            bx1 = int(max(0, px - width / 2))
            by1 = int(max(0, py - height / 2))
            bx2 = int(min(frame.shape[1] - 1, px + width / 2))
            by2 = int(min(frame.shape[0] - 1, py + height / 2))
            contours.append(np.array([[[bx1, by1]], [[bx2, by1]], [[bx2, by2]], [[bx1, by2]]], dtype=np.int32))
            detected_area += max(0, bx2 - bx1) * max(0, by2 - by1)

            class_name = str(pred.get("class", "pill"))
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
            confidences.append(float(pred.get("confidence", 0.0)))

        pill_count = len(contours)
        return SlotVisionResult(
            present=pill_count > 0,
            confidence=max(confidences) if confidences else 0.0,
            color_ratio=min(1.0, detected_area / slot_area),
            roi=(x1, y1, x2, y2),
            pill_count=pill_count,
            contours=contours,
            class_counts=class_counts,
        )


class LocalYoloPillDetector:
    """电脑端本地 YOLO 药丸检测器。

    适合加载从 Roboflow/Ultralytics 导出的药丸检测权重，例如 best.pt。
    注意：仓库里的 yolo11n.pt/yolo26n.pt 是 COCO 通用预训练权重，不是药丸专用模型。
    """
    EXPECTED_PILL_NAMES = {"capsule", "capsules", "tablet", "tablets", "pill", "pills"}

    def __init__(self, model_path, confidence=0.4):
        if not model_path:
            raise ValueError("使用本地 YOLO 检测器需要传入 --yolo-model，例如 --yolo-model best.pt")

        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"找不到 YOLO 权重文件：{model_path}")

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("使用本地 YOLO 检测器需要安装 ultralytics：pip install ultralytics") from exc

        self.model_path = model_path
        self.model = YOLO(str(model_path))
        self.confidence = confidence
        self.names = self.model.names

        model_class_names = {str(name).lower() for name in self.names.values()}
        self.allowed_class_names = model_class_names & self.EXPECTED_PILL_NAMES
        if not (model_class_names & self.EXPECTED_PILL_NAMES):
            print(
                "[WARNING] 当前 YOLO 权重的类别看起来不是药丸数据集；"
                "如果使用 yolo11n.pt/yolo26n.pt，检测到的是 COCO 通用物体，不适合药片识别。"
            )

    def detect_all(self, frame) -> dict[str, SlotVisionResult]:
        predictions = self._infer_frame(frame)
        return {
            key: self._build_slot_result(frame, key, predictions)
            for key in SLOTS_CONFIG
        }

    def detect(self, frame, slot_key) -> SlotVisionResult:
        return self.detect_all(frame)[slot_key]

    def _infer_frame(self, frame):
        results = self.model.predict(frame, conf=self.confidence, verbose=False)
        if not results:
            return []

        result = results[0]
        predictions = []
        if result.boxes is None:
            return predictions

        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            class_id = int(box.cls[0])
            class_name = str(self.names.get(class_id, class_id))
            if str(class_name).lower() not in self.allowed_class_names:
                continue
            confidence = float(box.conf[0])
            predictions.append({
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "x": (x1 + x2) / 2,
                "y": (y1 + y2) / 2,
                "width": x2 - x1,
                "height": y2 - y1,
                "class": class_name,
                "confidence": confidence,
            })
        return predictions

    def _build_slot_result(self, frame, slot_key, predictions):
        config = SLOTS_CONFIG[slot_key]
        x1, y1, x2, y2, cx, cy, radius = slot_geometry(frame.shape, config)
        slot_area = max(1, np.pi * radius * radius)

        contours = []
        class_counts = {}
        confidences = []
        detected_area = 0.0

        for pred in predictions:
            px = float(pred.get("x", 0.0))
            py = float(pred.get("y", 0.0))
            if (px - cx) ** 2 + (py - cy) ** 2 > radius ** 2:
                continue

            bx1 = int(max(0, pred.get("x1", px - pred.get("width", 0.0) / 2)))
            by1 = int(max(0, pred.get("y1", py - pred.get("height", 0.0) / 2)))
            bx2 = int(min(frame.shape[1] - 1, pred.get("x2", px + pred.get("width", 0.0) / 2)))
            by2 = int(min(frame.shape[0] - 1, pred.get("y2", py + pred.get("height", 0.0) / 2)))
            contours.append(np.array([[[bx1, by1]], [[bx2, by1]], [[bx2, by2]], [[bx1, by2]]], dtype=np.int32))
            detected_area += max(0, bx2 - bx1) * max(0, by2 - by1)

            class_name = str(pred.get("class", "pill"))
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
            confidences.append(float(pred.get("confidence", 0.0)))

        pill_count = len(contours)
        return SlotVisionResult(
            present=pill_count > 0,
            confidence=max(confidences) if confidences else 0.0,
            color_ratio=min(1.0, detected_area / slot_area),
            roi=(x1, y1, x2, y2),
            pill_count=pill_count,
            contours=contours,
            class_counts=class_counts,
        )


class MedicationTracker:
    """No-swallow 安全状态机：只基于视觉药量变化生成取药事件，并判断漏服、错格和剂量风险。"""

    def __init__(self, slot_keys):
        self.slot_keys = list(slot_keys)
        self.previous_present = {key: True for key in self.slot_keys}
        self.confirmed = {key: False for key in self.slot_keys}
        self.feedback = {
            key: SlotFeedback("ready", "READY", (100, 255, 100)) for key in self.slot_keys
        }
        self.last_status = {key: "ready" for key in self.slot_keys}
        self.streak_count = 0
        self.last_pill_count = {key: 0 for key in self.slot_keys}
        self.last_taken_count = {key: 0 for key in self.slot_keys}
        self.wrong_period_alarm = {key: False for key in self.slot_keys}
        self.stable_pill_count = {key: 0 for key in self.slot_keys}
        self.ema_pill_count = {key: None for key in self.slot_keys}
        self.event_baseline_count = {key: 0 for key in self.slot_keys}
        self.pending_take_event = {key: None for key in self.slot_keys}
        self.missed_alarm_sent = {key: False for key in self.slot_keys}
        self.last_period = CURRENT_PERIOD
        self.period_started_at = time.monotonic()
        self.system_state = "MONITORING"
        self.recovery_until = {key: 0.0 for key in self.slot_keys}

        self.led_status = "OFF"
        self.buzzer_status = "OFF"
        self.voice_status = "OFF"
        self.last_events = []

    def update(self, vision_results, now=None):
        global CURRENT_PERIOD
        now = time.monotonic() if now is None else now
        events = []

        if CURRENT_PERIOD != self.last_period:
            for key in self.slot_keys:
                self.wrong_period_alarm[key] = False
                self.missed_alarm_sent[key] = False
                self.confirmed[key] = False
                self.pending_take_event[key] = None
                self.event_baseline_count[key] = self.stable_pill_count[key]
            self.period_started_at = now
            self.last_period = CURRENT_PERIOD
            events.append(f"[INFO] 当前服药时段切换为 {SLOTS_CONFIG[CURRENT_PERIOD]['cn']}。")

        for key, result in vision_results.items():
            expected = MEDICATION_PLAN[key]["expected_count"]
            uncertain = self._is_uncertain(result)
            if uncertain:
                current_count = self.stable_pill_count[key]
                result.pill_count = current_count
                result.present = current_count > 0
                previous_count = self.event_baseline_count[key]
                taken_count = 0
                take_event = False
                self.pending_take_event[key] = None
                pending_confirmation = False
            else:
                current_count = self._update_stable_count(key, result.pill_count)
                result.pill_count = current_count
                result.present = current_count > 0
                previous_count, taken_count, take_event = self._update_take_event_candidate(key, current_count)
                pending_confirmation = self.pending_take_event[key] is not None
            status_event_emitted = False

            if take_event:
                self.last_taken_count[key] = taken_count
                self.last_pill_count[key] = taken_count
                events.append(
                    f"[EVENT] TAKE_MED_EVENT: {SLOTS_CONFIG[key]['cn']}药格 {previous_count}->{current_count}，取出 {taken_count} 粒。"
                )

            if key != CURRENT_PERIOD:
                if take_event:
                    self.wrong_period_alarm[key] = True
                    self.confirmed[key] = False
                    feedback = SlotFeedback("critical", f"WRONG SLOT TAKE: {taken_count}", (40, 40, 255))
                    events.append(
                        f"[CRITICAL] 孔位错误：当前应服 {SLOTS_CONFIG[CURRENT_PERIOD]['cn']}，但 {SLOTS_CONFIG[key]['cn']} 药格发生取药事件。"
                    )
                    status_event_emitted = True
                elif self.wrong_period_alarm[key] and result.present and current_count >= expected:
                    self.wrong_period_alarm[key] = False
                    self.recovery_until[key] = now + RECOVERY_DISPLAY_SECONDS
                    self.event_baseline_count[key] = current_count
                    self.pending_take_event[key] = None
                    feedback = SlotFeedback("recovery", "RECOVERY: PILLS RETURNED", (80, 240, 120))
                    events.append(f"[INFO] {SLOTS_CONFIG[key]['cn']} 药格已恢复，错格警报解除。")
                    status_event_emitted = True
                elif self.wrong_period_alarm[key]:
                    feedback = SlotFeedback("critical", f"WRONG SLOT LOCKED ({taken_count or self.last_taken_count[key]})", (40, 40, 255))
                elif self.recovery_until[key] > now:
                    feedback = SlotFeedback("recovery", "RECOVERY: BACK TO MONITOR", (80, 240, 120))
                elif uncertain:
                    feedback = SlotFeedback("uncertain", "UNCERTAIN: ADJUST CAMERA", (0, 210, 255))
                elif pending_confirmation:
                    feedback = SlotFeedback("waiting", "VERIFYING TAKE EVENT", (60, 220, 255))
                elif result.present:
                    self.last_pill_count[key] = current_count
                    feedback = self._build_loaded_feedback(result, expected)
                else:
                    feedback = SlotFeedback("empty_normal", "EMPTY / READY", (180, 180, 180))
            else:
                self.wrong_period_alarm[key] = False

                if self.recovery_until[key] > now:
                    feedback = SlotFeedback("recovery", "RECOVERY: BACK TO MONITOR", (80, 240, 120))
                elif uncertain:
                    feedback = SlotFeedback("uncertain", "UNCERTAIN: ADJUST CAMERA", (0, 210, 255))
                elif take_event:
                    self.missed_alarm_sent[key] = False
                    if taken_count == expected:
                        self.confirmed[key] = True
                        self.streak_count += 1
                        feedback = SlotFeedback("confirmed", f"TAKE EVENT OK: {taken_count}", (80, 240, 120))
                        events.append(
                            f"[INFO] 正常取药：{SLOTS_CONFIG[key]['cn']}药格取出 {taken_count} 粒，符合处方 {expected} 粒。"
                        )
                        if self.streak_count % 3 == 0:
                            events.append(self._format_event(key, "reward", streak_count=self.streak_count))
                    else:
                        self.confirmed[key] = False
                        self.streak_count = 0
                        feedback = SlotFeedback("warning", f"DOSAGE ERROR: TAKEN {taken_count}/{expected}", (0, 102, 255))
                        events.append(
                            f"[WARNING] 剂量异常：{SLOTS_CONFIG[key]['cn']}药格应取 {expected} 粒，实际取出 {taken_count} 粒。"
                        )
                    status_event_emitted = True
                elif self.confirmed[key] and current_count <= max(0, expected - self.last_taken_count[key]):
                    feedback = SlotFeedback("confirmed", f"TAKE EVENT OK: {self.last_taken_count[key]}", (80, 240, 120))
                elif pending_confirmation:
                    feedback = SlotFeedback("waiting", "VERIFYING TAKE EVENT", (60, 220, 255))
                elif result.present:
                    self.last_pill_count[key] = current_count
                    if now - self.period_started_at >= MISSED_REMINDER_DELAY:
                        feedback = SlotFeedback("missed", "MISSED RISK: NO TAKE EVENT", (60, 220, 255))
                        if not self.missed_alarm_sent[key]:
                            self.missed_alarm_sent[key] = True
                            events.append(
                                f"[WARNING] 漏服风险：{SLOTS_CONFIG[key]['cn']}服药时段内药丸数量未变化，请提醒老人服药。"
                            )
                            status_event_emitted = True
                    else:
                        feedback = self._build_loaded_feedback(result, expected)
                else:
                    feedback = SlotFeedback("empty_normal", "EMPTY / NO EVENT", (180, 180, 180))

            if feedback.status != self.last_status[key]:
                if not status_event_emitted:
                    events.append(self._format_event(key, feedback.status))
                self.last_status[key] = feedback.status

            self.feedback[key] = feedback
            self.previous_present[key] = result.present

        self.last_events = events
        self.update_hardware_state(now)
        return self.feedback, events

    def _is_uncertain(self, result):
        """只对检测到药丸但置信度偏低的画面暂停判定，避免把空药格误报为不确定。"""
        return result.present and 0.0 < result.confidence < DETECTION_CONFIDENCE_THRESHOLD

    def _update_stable_count(self, slot_key, raw_count):
        """用 EMA 抑制 pill_count 帧间抖动，再四舍五入为业务计数。"""
        raw_count = max(0, int(raw_count))
        previous_ema = self.ema_pill_count[slot_key]
        if previous_ema is None:
            ema = float(raw_count)
        else:
            ema = PILL_COUNT_EMA_ALPHA * raw_count + (1.0 - PILL_COUNT_EMA_ALPHA) * previous_ema

        stable_count = max(0, int(round(ema)))
        self.ema_pill_count[slot_key] = ema
        self.stable_pill_count[slot_key] = stable_count

        if stable_count > self.event_baseline_count[slot_key]:
            self.event_baseline_count[slot_key] = stable_count
            self.pending_take_event[slot_key] = None

        return stable_count

    def _update_take_event_candidate(self, slot_key, current_count):
        """只有同一数量下降持续多帧，才确认 TAKE_MED_EVENT。"""
        baseline = self.event_baseline_count[slot_key]
        if current_count >= baseline:
            self.pending_take_event[slot_key] = None
            return baseline, 0, False

        taken_count = baseline - current_count
        pending = self.pending_take_event[slot_key]
        if pending and pending["from"] == baseline and pending["to"] == current_count:
            pending["frames"] += 1
        else:
            pending = {"from": baseline, "to": current_count, "taken": taken_count, "frames": 1}
            self.pending_take_event[slot_key] = pending

        if pending["frames"] < TAKE_EVENT_CONFIRM_FRAMES:
            return baseline, taken_count, False

        self.event_baseline_count[slot_key] = current_count
        self.pending_take_event[slot_key] = None
        return baseline, taken_count, True

    @staticmethod
    def _build_loaded_feedback(result, expected):
        if result.pill_count == expected:
            return SlotFeedback("ready", f"READY / Pills: {result.pill_count}", (100, 255, 100))
        return SlotFeedback("wrong_ready", f"WRONG DOSAGE ({result.pill_count}/{expected})", (0, 102, 255))

    def update_hardware_state(self, now):
        """根据当前药格与日志状态，计算声光报警器的模拟输出指标"""
        self.led_status = "OFF"
        self.buzzer_status = "OFF"
        self.voice_status = "OFF"
        self.system_state = "MONITORING"

        has_critical = any(fb.status == "critical" for fb in self.feedback.values()) or any(self.wrong_period_alarm.values())
        has_uncertain = any(fb.status == "uncertain" for fb in self.feedback.values())
        has_recovery = any(fb.status == "recovery" for fb in self.feedback.values())
        
        has_warning_dosage = any(
            fb.status == "warning" and "DOSAGE ERROR" in fb.text
            for fb in self.feedback.values()
        )
        has_missed = any(fb.status == "missed" for fb in self.feedback.values())
                
        has_confirmed = any(fb.status == "confirmed" for fb in self.feedback.values())
        has_waiting = any(fb.status in ("waiting", "warning") for fb in self.feedback.values())

        if has_critical:
            self.system_state = "LOCKED_WRONG_SLOT" if any(self.wrong_period_alarm.values()) else "REMINDER"
            self.led_status = "RED"
            self.buzzer_status = "ALARM"
            # 优先提示拿错时段
            if any(self.wrong_period_alarm.values()) or any("拿错" in str(evt) or "错误时间段" in str(evt) for evt in self.last_events):
                self.voice_status = "WRONG_SLOT"
            else:
                self.voice_status = "URGENT_CONFIRM"
        elif has_warning_dosage:
            self.system_state = "WARNING_DOSAGE"
            self.led_status = "RED"
            self.buzzer_status = "ALARM"
            self.voice_status = "DOSAGE_ERROR"
        elif has_uncertain:
            self.system_state = "UNCERTAIN"
            self.led_status = "YELLOW"
            self.buzzer_status = "OFF"
            self.voice_status = "ADJUST_CAMERA"
        elif has_recovery:
            self.system_state = "RECOVERY"
            self.led_status = "GREEN"
            self.buzzer_status = "SHORT_BEEP"
            self.voice_status = "RECOVERY_OK"
        elif has_confirmed:
            self.system_state = "NORMAL_SUCCESS"
            self.led_status = "GREEN"
            self.buzzer_status = "SHORT_BEEP"
            self.voice_status = "NORMAL_CONFIRMED"
        elif has_missed:
            self.system_state = "MISSED_RISK"
            self.led_status = "YELLOW"
            self.buzzer_status = "OFF"
            self.voice_status = "REMIND_TAKE"
        elif has_waiting:
            self.system_state = "NORMAL_IN_PROGRESS"
            self.led_status = "YELLOW"
            self.buzzer_status = "OFF"
            self.voice_status = "OFF"


    @staticmethod
    def _format_event(slot_key, status, **details):
        cn_name = SLOTS_CONFIG[slot_key]["cn"]

        if status == "confirmed":
            return f"[INFO] {cn_name}药格取药事件已确认：数量变化符合处方。"
        if status == "waiting":
            return f"[INFO] {cn_name}药格等待取药事件。"
        if status == "warning":
            return f"[WARNING] {cn_name}药格剂量异常：请核对取出数量。"
        if status == "missed":
            return f"[WARNING] {cn_name}时段内未检测到取药事件：触发漏服提醒。"
        if status == "critical":
            return f"[CRITICAL] {cn_name}药格发生错误时段取药事件：建议立即干预。"
        if status == "reward":
            streak = details.get("streak_count", 0)
            return f"[REWARD] 连续按时服药 {streak} 次：解锁亲情照片盲盒奖励。"
        if status == "ready":
            return f"[INFO] {cn_name}药格检测到药丸：等待数量变化。"
        return f"[INFO] {cn_name}药格状态更新：{status}。"


def slot_geometry(frame_shape, config):
    height, width = frame_shape[:2]
    cx = int(width * config["center_ratio"][0])
    cy = int(height * config["center_ratio"][1])
    radius = max(26, int(min(width, height) * 0.115))
    x1 = max(0, cx - radius)
    y1 = max(0, cy - radius)
    x2 = min(width, cx + radius)
    y2 = min(height, cy + radius)
    return x1, y1, x2, y2, cx, cy, radius


def offset_contours(contours, x_offset, y_offset):
    shifted = []
    for contour in contours:
        moved = contour.copy()
        moved[:, :, 0] += x_offset
        moved[:, :, 1] += y_offset
        shifted.append(moved)
    return shifted


# ==========================================
# PIL 高端看板绘制层
# ==========================================

def draw_top_banner_pil(draw, tracker):
    """绘制精美的系统顶部状态卡片栏"""
    font_title = get_font(15, bold=True)
    font_sub = get_font(10)
    font_info = get_font(11, bold=True)
    
    # 绘制深底板
    draw.rectangle([0, 0, 900, 64], fill=(20, 24, 30, 255))
    draw.line([0, 64, 900, 64], fill=(80, 85, 95, 255), width=1)
    
    # 左侧系统名称
    draw.text((20, 13), "记忆回音 · 阿尔茨海默症辅助服药系统 V4.0", font=font_title, fill=(255, 255, 255, 255))
    draw.text((20, 36), "Memory Echo Smart Pillbox Monitor", font=font_sub, fill=(150, 155, 165, 255))
    
    if tracker is not None:
        state_str = f"状态机: {tracker.system_state}"
        streak_str = f"连续正确取药: {tracker.streak_count} 次"
        draw.text((900 - 450, 22), state_str, font=font_info, fill=(80, 220, 255, 255))
        draw.text((900 - 240, 22), streak_str, font=font_info, fill=(255, 215, 0, 255))


def draw_slot_overlay_pil(draw, vision_results, feedback, tracker, frame_shape=None):
    """为早中晚药格绘制半透明磨砂圆角信息卡片与状态彩色徽章"""
    font_title = get_font(12, bold=True)
    font_text = get_font(11)
    font_badge = get_font(10, bold=True)
    frame_w = frame_shape[1] if frame_shape is not None else max(result.roi[2] for result in vision_results.values())
    card_w = min(230, max(180, int(frame_w * 0.20)))
    card_h = 85
    gap_to_slot = 14
    safe_top = 76

    for key, config in SLOTS_CONFIG.items():
        result = vision_results[key]
        slot_feedback = feedback[key]
        
        x1, y1, x2, y2 = result.roi
        cx = (x1 + x2) // 2

        card_x1 = min(max(8, cx - card_w // 2), max(8, frame_w - card_w - 8))
        card_x2 = card_x1 + card_w
        card_y2 = max(safe_top + card_h, y1 - gap_to_slot)
        card_y1 = card_y2 - card_h

        status = slot_feedback.status
        status_text = slot_feedback.text
        
        border_color = (120, 125, 135)
        badge_bg = (100, 105, 115, 255)
        badge_text_color = (255, 255, 255, 255)
        badge_str = "状态未知"
        
        expected = MEDICATION_PLAN[key]["expected_count"]
        
        if status == "ready":
            border_color = (80, 240, 120)  # 绿色
            badge_bg = (40, 180, 80, 255)
            badge_str = "药量正确 · 待服用"
        elif status == "wrong_ready":
            border_color = (255, 140, 0)   # 橙色
            badge_bg = (230, 110, 20, 255)
            badge_str = "装药异常 · 请核对"
        elif status == "waiting":
            border_color = (255, 210, 0)   # 黄色
            badge_bg = (210, 170, 0, 255)
            badge_text_color = (30, 30, 30, 255)
            badge_str = "取药事件处理中"
        elif status == "warning":
            if "DOSAGE ERROR" in status_text:
                border_color = (255, 100, 0)  # 橙色
                badge_bg = (230, 80, 10, 255)
                badge_str = "服药数量异常！"
            else:
                border_color = (255, 210, 0)  # 黄色
                badge_bg = (210, 170, 0, 255)
                badge_text_color = (30, 30, 30, 255)
                badge_str = "请核对药量"
        elif status == "missed":
            border_color = (255, 210, 0)
            badge_bg = (210, 170, 0, 255)
            badge_text_color = (30, 30, 30, 255)
            badge_str = "漏服风险 · 请提醒"
        elif status == "uncertain":
            border_color = (0, 210, 255)
            badge_bg = (0, 150, 210, 255)
            badge_str = "视觉不确定 · 请调整画面"
        elif status == "recovery":
            border_color = (80, 240, 120)
            badge_bg = (40, 180, 80, 255)
            badge_str = "已恢复监控"
        elif status == "confirmed":
            border_color = (80, 240, 120)  # 绿色
            badge_bg = (40, 180, 80, 255)
            badge_str = "正确取药已确认"
        elif status == "critical":
            border_color = (255, 40, 40)   # 红色
            badge_bg = (220, 30, 30, 255)
            if "WRONG PERIOD" in status_text:
                badge_str = "警告：拿错时间段！"
            else:
                badge_str = "严重警告：错误取药！"
        elif status == "empty_normal":
            border_color = (120, 125, 135)  # 灰色
            badge_bg = (100, 105, 115, 255)
            badge_str = "空置就绪"

        # 1. 绘制半透明卡片背景（Glassmorphism 效果：RGBA 填充底色 + 极细白色半透明高光描边）
        draw.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=10, fill=(24, 28, 36, 170), outline=(255, 255, 255, 40), width=1)
        
        # 2. 卡片内侧微光发光圈（随状态映射对应颜色，深度融合）
        inner_glow_color = border_color + (90,)  # 增加透明度通道作为发光微澜
        draw.rounded_rectangle([card_x1 + 1, card_y1 + 1, card_x2 - 1, card_y2 - 1], radius=9, fill=None, outline=inner_glow_color, width=1)
        
        # 写入标题与处方对比数据
        draw.text((card_x1 + 12, card_y1 + 10), f"{config['cn']}药格 ({config['name']})", font=font_title, fill=(255, 255, 255, 255))
        
        if result.present:
            actual = result.pill_count
            class_text = ""
            if result.class_counts:
                class_text = "  |  " + ", ".join(
                    f"{name}:{count}" for name, count in sorted(result.class_counts.items())
                )
            info_str = f"处方: {expected} 粒  |  当前: {actual} 粒{class_text}"
            info_color = (220, 225, 235, 255)
        else:
            actual = tracker.last_pill_count[key] if tracker is not None else expected
            info_str = f"处方: {expected} 粒  |  取出: {actual} 粒"
            info_color = (160, 165, 175, 255)
            
        draw.text((card_x1 + 12, card_y1 + 32), info_str, font=font_text, fill=info_color)
        
        # 绘制状态圆角徽章
        badge_rect = [card_x1 + 12, card_y1 + 54, card_x2 - 12, card_y1 + 74]
        draw_badge(draw, badge_str, badge_rect, badge_bg, badge_text_color, font_badge)


def draw_hardware_panel_pil(draw, tracker, frame_shape=None):
    """绘制虚拟声光联动模拟看板，提供酷炫的 LED 光晕发光效果"""
    panel_w, panel_h = 420, 118
    panel_x1 = 240
    panel_x2 = panel_x1 + panel_w
    panel_y1 = 70
    panel_y2 = panel_y1 + panel_h
    if frame_shape is not None:
        height, width = frame_shape[:2]
        radius = max(26, int(min(width, height) * 0.115))
        card_h = 85
        gap_to_slot = 14
        safe_top = 76
        slot_card_top = min(
            max(safe_top, max(0, int(height * config["center_ratio"][1]) - radius) - gap_to_slot - card_h)
            for config in SLOTS_CONFIG.values()
        )
        panel_w = min(620, max(420, int(width * 0.46)))
        panel_x1 = (width - panel_w) // 2
        panel_x2 = panel_x1 + panel_w
        panel_y2 = slot_card_top - 16
        panel_y1 = max(70, panel_y2 - panel_h)

    font_text = get_font(11)
    panel_height = panel_y2 - panel_y1

    # 1. 绘制半透明磨砂效果面板背景（半透明深色填充 + 极细白色高光描边）
    draw.rounded_rectangle([panel_x1, panel_y1, panel_x2, panel_y2], radius=12, fill=(24, 28, 36, 170), outline=(255, 255, 255, 40), width=1)
    
    # 2. 内圈白色软微光描边，提升卡片边缘的通透感
    draw.rounded_rectangle([panel_x1 + 1, panel_y1 + 1, panel_x2 - 1, panel_y2 - 1], radius=11, fill=None, outline=(255, 255, 255, 25), width=1)
    
    # 计算 LED 灯中心位置
    cx_led, cy_led = panel_x1 + 35, panel_y1 + panel_height // 2
    r_led = 9

    # 渲染 LED 模拟指示灯光晕（仅视觉，不影响 tracker）
    if tracker.led_status == "GREEN":
        draw_glow_led(draw, cx_led, cy_led, r_led, (80, 240, 120, 255), (40, 120, 60, 140), (20, 60, 30, 60))
    elif tracker.led_status == "YELLOW":
        draw_glow_led(draw, cx_led, cy_led, r_led, (255, 210, 0, 255), (130, 105, 0, 140), (65, 50, 0, 60))
    elif tracker.led_status == "RED":
        if int(time.time() * 2) % 2 == 0:
            draw_glow_led(draw, cx_led, cy_led, r_led, (255, 40, 40, 255), (130, 20, 20, 140), (65, 10, 10, 60))
        else:
            draw_glow_led(draw, cx_led, cy_led, r_led, (80, 20, 20, 255), (40, 10, 10, 100), (30, 5, 5, 50))
    else:
        draw_glow_led(draw, cx_led, cy_led, r_led, (100, 100, 100, 255), (60, 60, 60, 100), (40, 40, 40, 50))
        
    # UI 单行状态文案（仅渲染层，不修改 tracker）
    period_cn = SLOTS_CONFIG[CURRENT_PERIOD]["cn"]
    title_seg = f"[仿真] {period_cn}"
    if tracker.led_status == "GREEN":
        led_seg = "🟢 正常"
    elif tracker.led_status == "YELLOW":
        led_seg = "🟡 待取"
    elif tracker.led_status == "RED":
        led_seg = "🔴 警报"
    else:
        led_seg = "⚪ 待机"

    voice_seg = "🔊 静音"
    line_color = (200, 205, 215, 255)
    if tracker.voice_status == "NORMAL_CONFIRMED":
        voice_seg = "🔊 已确认"
        line_color = (80, 240, 120, 255)
    elif tracker.voice_status == "DOSAGE_ERROR":
        voice_seg = "🔊 剂量错"
        line_color = (255, 140, 0, 255)
    elif tracker.voice_status == "WRONG_SLOT":
        voice_seg = "🔊 拿错药格!"
        line_color = (255, 40, 40, 255)
    elif tracker.voice_status == "URGENT_CONFIRM":
        voice_seg = "🔊 请取药"
        line_color = (255, 210, 0, 255)
    elif tracker.voice_status == "ADJUST_CAMERA":
        voice_seg = "🔊 调整画面"
        line_color = (0, 210, 255, 255)
    elif tracker.voice_status == "RECOVERY_OK":
        voice_seg = "🔊 已恢复"
        line_color = (80, 240, 120, 255)
    elif tracker.voice_status == "REMIND_TAKE":
        voice_seg = "🔊 请取药"
        line_color = (255, 210, 0, 255)
    elif tracker.led_status == "GREEN":
        line_color = (80, 240, 120, 255)
    elif tracker.led_status == "YELLOW":
        line_color = (255, 210, 0, 255)
    elif tracker.led_status == "RED":
        line_color = (255, 40, 40, 255)

    status_line = f"{title_seg} | {led_seg} | {voice_seg}".replace("\n", " ")
    max_text_width = panel_w - 70
    while len(status_line) > 8:
        try:
            bbox = draw.textbbox((0, 0), status_line, font=font_text)
            text_width = bbox[2] - bbox[0]
        except AttributeError:
            text_width, _ = draw.textsize(status_line, font=font_text)
        if text_width <= max_text_width:
            break
        if len(voice_seg) > 4:
            voice_seg = voice_seg[:-1]
        else:
            status_line = status_line[: max(0, len(status_line) - 4)] + "..."
            break
        status_line = f"{title_seg} | {led_seg} | {voice_seg}".replace("\n", " ")

    text_x = panel_x1 + 58
    try:
        bbox = draw.textbbox((0, 0), status_line, font=font_text)
        text_height = bbox[3] - bbox[1]
        offset_y = bbox[1]
    except AttributeError:
        _, text_height = draw.textsize(status_line, font=font_text)
        offset_y = 0
    text_y = panel_y1 + (panel_height - text_height) // 2 - offset_y
    draw.text((text_x, text_y), status_line, font=font_text, fill=line_color)


def process_frame(frame, tracker=None, detector=None):
    if detector is None:
        detector = PillDetector()
    output = frame.copy()
    
    # 1. 视觉检测提取
    if hasattr(detector, "detect_all"):
        vision_results = detector.detect_all(frame)
    else:
        vision_results = {
            key: detector.detect(frame, key) for key in SLOTS_CONFIG
        }

    # 2. 状态逻辑更新
    if tracker is None:
        feedback = {
            key: SlotFeedback(
                "ready" if result.present else "waiting",
                "FULL / NOT TAKEN" if result.present else "EMPTY",
                (100, 255, 100) if result.present else (60, 220, 255),
            )
            for key, result in vision_results.items()
        }
        events = []
    else:
        feedback, events = tracker.update(vision_results)

    # 3. 绘制底层的 OpenCV 矢量元素（抗锯齿的药格圆环和药丸轮廓）
    for key, config in SLOTS_CONFIG.items():
        result = vision_results[key]
        x1, y1, x2, y2 = result.roi
        _, _, _, _, cx, cy, radius = slot_geometry(output.shape, config)
        
        # 药格定位圈 (BGR)
        cv2.circle(output, (cx, cy), radius, config["color"], 2, lineType=cv2.LINE_AA)
        # Bounding box 限制框
        cv2.rectangle(output, (x1, y1), (x2, y2), (60, 62, 66), 1)
        # 药丸轮廓线
        for contour in result.contours:
            cv2.drawContours(output, [contour], -1, config["color"], 2, lineType=cv2.LINE_AA)

    # 4. 转换至 PIL RGBA 分层透明通道，开始高精度的毛玻璃渲染
    # img_base：主图层 (RGBA)
    img_base = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB)).convert("RGBA")
    # img_overlay：半透明覆盖层 (RGBA)，用于混合毛玻璃的 Alpha 像素
    img_overlay = Image.new("RGBA", img_base.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(img_overlay)

    # 绘制实心顶部 Banner 看板（直接画在 img_base 上以保留高性能）
    draw_top_banner_pil(ImageDraw.Draw(img_base), tracker)
    
    # 绘制悬浮信息卡片（画在半透明覆盖层上）
    draw_slot_overlay_pil(draw_overlay, vision_results, feedback, tracker, output.shape)
    
    # 绘制硬件联动模拟板（画在半透明覆盖层上）
    if tracker is not None:
        draw_hardware_panel_pil(draw_overlay, tracker, output.shape)

    # 5. 使用 PIL Alpha 混合完成融合成品图像，并还原为 OpenCV BGR 格式
    img_final = Image.alpha_composite(img_base, img_overlay).convert("RGB")
    output = cv2.cvtColor(np.array(img_final), cv2.COLOR_RGB2BGR)

    return output, vision_results, feedback, events


def draw_pill(img, center, r, color):
    # 绘制药丸圆形主体
    cv2.circle(img, center, r, color, -1, lineType=cv2.LINE_AA)
    # 绘制白色的反光高光以提升检测轮廓的分离度，完美避开粘连
    cv2.circle(img, (center[0] - r // 3, center[1] - r // 3), r // 3, (245, 245, 245), -1, lineType=cv2.LINE_AA)


def draw_simulator_scene(slot_states):
    img = np.full((560, 900, 3), (42, 45, 48), dtype=np.uint8)

    # 绘制药盒主体大边框
    cv2.rectangle(img, (70, 210), (830, 440), (62, 65, 68), -1)
    cv2.rectangle(img, (70, 210), (830, 440), (122, 126, 130), 2)
    
    # 底部按键操作说明提示
    cv2.putText(img, "SIMULATOR: r/g/b cycle count, SPACE take current slot, t period, q quit",
                (78, 475), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (190, 210, 230), 1, cv2.LINE_AA)

    for key, config in SLOTS_CONFIG.items():
        _, _, _, _, cx, cy, radius = slot_geometry(img.shape, config)
        # 药格深色凹槽背景
        cv2.circle(img, (cx, cy), radius + 10, (85, 85, 88), -1, lineType=cv2.LINE_AA)
        cv2.circle(img, (cx, cy), radius + 10, (145, 145, 150), 2, lineType=cv2.LINE_AA)
        
        count = slot_states[key]
        if count == 0:
            # 空药槽
            cv2.circle(img, (cx, cy), radius - 8, (38, 38, 40), -1, lineType=cv2.LINE_AA)
        else:
            # 有药状态底板
            cv2.circle(img, (cx, cy), radius - 8, (48, 50, 52), -1, lineType=cv2.LINE_AA)
            
            # 排列绘制药片（带高光反光），并相比 V3.1 显著增大间距，解决重叠融合造成的数量识别错误
            pill_r = 10
            if count == 1:
                draw_pill(img, (cx, cy), pill_r, config["color"])
            elif count == 2:
                # 将间距拉大到两边，避免 5x5 的 MORPH_CLOSE 闭运算将其重连
                draw_pill(img, (cx - 20, cy), pill_r, config["color"])
                draw_pill(img, (cx + 20, cy), pill_r, config["color"])
            elif count >= 3:
                # 三角排列的间距拉开，中心距离大于 36px 以上，实现完美分离检测
                draw_pill(img, (cx, cy - 20), pill_r, config["color"])
                draw_pill(img, (cx - 18, cy + 15), pill_r, config["color"])
                draw_pill(img, (cx + 18, cy + 15), pill_r, config["color"])

    draw_person_panel(img)
    return img


def draw_person_panel(img):
    """绘制右侧被监护人简易画像。No-swallow 版本不模拟手势或吞咽。"""
    face_center = (690, 125)
    mouth = (690, 148)
    cv2.circle(img, face_center, 52, (205, 185, 165), -1, lineType=cv2.LINE_AA)
    cv2.circle(img, (670, 110), 5, (40, 40, 40), -1, lineType=cv2.LINE_AA)
    cv2.circle(img, (710, 110), 5, (40, 40, 40), -1, lineType=cv2.LINE_AA)
    cv2.ellipse(img, mouth, (20, 8), 0, 0, 180, (60, 60, 60), 2, lineType=cv2.LINE_AA)
    cv2.line(img, (690, 177), (690, 205), (190, 170, 150), 8, lineType=cv2.LINE_AA)


def print_intro(use_camera):
    print("==================================================")
    print(" 阿尔茨海默症长者“记忆回音药盒”视觉识别原型 V4.0")
    print("==================================================")
    print("视觉任务：Roboflow YOLO 药丸检测 + OpenCV 药格映射 + V4 安全状态机")
    print("按键说明：")
    print("  r     : 循环切换“早上(Morning)”药格药片数 (0->1->2->3->0)")
    print("  g     : 循环切换“中午(Noon)”药格药片数")
    print("  b     : 循环切换“晚上(Evening)”药格药片数")
    print("  Space : 模拟当前时段药格被取空，连续确认后生成 TAKE_MED_EVENT")
    print("  t     : 循环切换当前系统服药时间段 (Morning->Noon->Evening->Morning)")
    print("  q     : 退出程序")
    print("模式：", "摄像头识别 + 键盘药格模拟" if use_camera else "无摄像头模拟器")
    print("==================================================")


def open_camera(camera_index, backend_preference="auto"):
    """打开摄像头并预读一帧，Windows 下优先避开容易报错的 MSMF 后端。"""
    backend_map = {
        "dshow": ("DirectShow", cv2.CAP_DSHOW),
        "msmf": ("MSMF", cv2.CAP_MSMF),
        "default": ("系统默认", cv2.CAP_ANY),
    }

    if backend_preference == "auto":
        if os.name == "nt":
            candidates = [backend_map["dshow"], backend_map["msmf"], backend_map["default"]]
        else:
            candidates = [backend_map["default"]]
    else:
        candidates = [backend_map[backend_preference]]

    for backend_name, backend_flag in candidates:
        cap = cv2.VideoCapture(camera_index, backend_flag)
        if not cap.isOpened():
            cap.release()
            continue

        ok, frame = cap.read()
        if ok and frame is not None:
            print(f"摄像头已打开：index={camera_index}, backend={backend_name}")
            return cap, backend_name

        print(f"摄像头后端 {backend_name} 已打开但读取失败，尝试下一个后端。")
        cap.release()

    return None, None


def handle_keypress(key, slot_states):
    global CURRENT_PERIOD
    if key == ord("q"):
        return True
    
    if key == ord("r"):
        slot_states["Morning"] = (slot_states["Morning"] + 1) % 4
        print(f"模拟器更新：早上药格内药片数量循环设为 {slot_states['Morning']}")
    elif key == ord("g"):
        slot_states["Noon"] = (slot_states["Noon"] + 1) % 4
        print(f"模拟器更新：中午药格内药片数量循环设为 {slot_states['Noon']}")
    elif key == ord("b"):
        slot_states["Evening"] = (slot_states["Evening"] + 1) % 4
        print(f"模拟器更新：晚上药格内药片数量循环设为 {slot_states['Evening']}")
    elif key == ord(" "):
        slot_states[CURRENT_PERIOD] = 0
        print(f"模拟器更新：当前时段【{CURRENT_PERIOD}】药格已取空，连续确认后生成 TAKE_MED_EVENT")
        
    elif key == ord("t"):
        if CURRENT_PERIOD == "Morning":
            CURRENT_PERIOD = "Noon"
        elif CURRENT_PERIOD == "Noon":
            CURRENT_PERIOD = "Evening"
        else:
            CURRENT_PERIOD = "Morning"
        print(f"模拟器更新：当前系统时段切换为【{CURRENT_PERIOD}】")
    return False


def create_detector_from_args(args):
    if args.detector == "auto":
        if args.roboflow_api_key:
            try:
                detector = RoboflowPillDetector(
                    api_key=args.roboflow_api_key,
                    confidence=args.roboflow_confidence,
                    overlap=args.roboflow_overlap,
                )
                print("检测后端：Roboflow pill-detection-fnftd/3（推荐主方案）")
                return detector
            except Exception as exc:
                print(f"[WARNING] Roboflow 初始化失败，回退到本地 OpenCV：{exc}")
        else:
            print("[INFO] 未设置 ROBOFLOW_API_KEY，自动使用本地 OpenCV 模拟检测。")
        print("检测后端：本地 OpenCV 颜色/轮廓检测")
        return PillDetector()

    if args.detector == "yolo":
        detector = LocalYoloPillDetector(
            model_path=args.yolo_model,
            confidence=args.yolo_confidence,
        )
        print(f"检测后端：本地 YOLO（{args.yolo_model}）")
        return detector

    if args.detector == "roboflow":
        if not args.roboflow_api_key:
            raise SystemExit("错误：使用 --detector roboflow 需要设置 ROBOFLOW_API_KEY 或传入 --roboflow-api-key")
        detector = RoboflowPillDetector(
            api_key=args.roboflow_api_key,
            confidence=args.roboflow_confidence,
            overlap=args.roboflow_overlap,
        )
        print("检测后端：Roboflow pill-detection-fnftd/3（capsules/tablets 目标检测）")
        return detector

    print("检测后端：本地 OpenCV 颜色/轮廓检测")
    return PillDetector()


def save_demo_snapshot(path, detector=None):
    """保存一张模拟器识别结果的精美截图"""
    global CURRENT_PERIOD
    CURRENT_PERIOD = "Morning"
    # 早上放2颗，中午放1颗，晚上放3颗。然后晚上拿走1颗触发拿错药警报！
    slot_states = {"Morning": 2, "Noon": 1, "Evening": 3}
    tracker = MedicationTracker(SLOTS_CONFIG.keys())
    if detector is None:
        detector = PillDetector()
    
    # 首先更新一帧，记录初始装药量（3颗）
    frame_init = draw_simulator_scene(slot_states)
    tracker.update({
        "Morning": SlotVisionResult(True, 1.0, 0.1, (0,0,10,10), 2),
        "Noon": SlotVisionResult(True, 1.0, 0.1, (0,0,10,10), 1),
        "Evening": SlotVisionResult(True, 1.0, 0.1, (0,0,10,10), 3)
    })
    
    # 模拟拿走一颗药
    slot_states["Evening"] = 2
    frame = draw_simulator_scene(slot_states)
    events = []
    processed = frame
    for _ in range(TAKE_EVENT_CONFIRM_FRAMES):
        processed, _, _, events = process_frame(frame, tracker, detector)
    
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), processed)
    for event in events:
        print("EVENT:", event)
    print(f"已保存演示截图：{path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Memory Echo Pillbox YOLO/OpenCV prototype V4.0")
    parser.add_argument("--camera-index", type=int, default=0, help="摄像头编号，默认 0")
    parser.add_argument(
        "--camera-backend",
        choices=("auto", "dshow", "msmf", "default"),
        default="auto",
        help="摄像头后端：Windows 推荐 auto/dshow；MSMF 报错时可显式使用 dshow",
    )
    parser.add_argument("--no-camera", action="store_true", help="强制使用模拟器")
    parser.add_argument("--no-camera-mirror", action="store_true", help="关闭摄像头水平镜像翻转")
    parser.add_argument("--snapshot", type=str, help="保存一张模拟器识别结果截图后退出")
    parser.add_argument(
        "--detector",
        choices=("auto", "opencv", "yolo", "roboflow"),
        default="auto",
        help="药丸检测后端：auto 优先 Roboflow，缺少 API key 时回退 OpenCV；roboflow 为云端 YOLOv11",
    )
    parser.add_argument("--yolo-model", default="best.pt", help="本地 YOLO 药丸检测权重路径，例如从 Roboflow 导出的 best.pt")
    parser.add_argument("--yolo-confidence", type=float, default=0.4, help="本地 YOLO 检测置信度阈值")
    parser.add_argument("--roboflow-api-key", default=os.getenv("ROBOFLOW_API_KEY"), help="Roboflow API key，也可用环境变量 ROBOFLOW_API_KEY")
    parser.add_argument("--roboflow-confidence", type=float, default=0.4, help="Roboflow 检测置信度阈值")
    parser.add_argument("--roboflow-overlap", type=float, default=0.3, help="Roboflow NMS overlap 阈值")
    return parser.parse_args()


def main():
    global CURRENT_PERIOD
    args = parse_args()

    detector = create_detector_from_args(args)

    if args.snapshot:
        save_demo_snapshot(args.snapshot, detector)
        return

    # 早上默认有2粒（正确用量），中午1粒（正确），晚上3粒（正确）
    slot_states = {"Morning": 2, "Noon": 1, "Evening": 3}
    tracker = MedicationTracker(SLOTS_CONFIG.keys())

    cap = None
    use_camera = False
    if not args.no_camera:
        cap, _ = open_camera(args.camera_index, args.camera_backend)
        use_camera = cap is not None and cap.isOpened()

    print_intro(use_camera)

    if not use_camera and cap is not None:
        cap.release()

    cv2.namedWindow(WINDOW_NAME)

    while True:
        if use_camera:
            ret, frame = cap.read()
            if not ret:
                print("摄像头画面读取失败，已切换为模拟器。")
                use_camera = False
                if cap is not None:
                    cap.release()
                continue
            frame = cv2.resize(frame, (900, 560))
            if not args.no_camera_mirror:
                cv2.flip(frame, 1, frame)
        else:
            frame = draw_simulator_scene(slot_states)

        processed, _, _, events = process_frame(frame, tracker, detector)
        for event in events:
            print("反馈事件：", event)

        cv2.imshow(WINDOW_NAME, processed)
        key = cv2.waitKey(30) & 0xFF
        if handle_keypress(key, slot_states):
            break

    if cap is not None and cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()
    print("程序已安全退出。")


if __name__ == "__main__":
    main()
