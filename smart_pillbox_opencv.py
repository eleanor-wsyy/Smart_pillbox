import argparse
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
# 小组作业更新：已加入摄像头 cv2.flip 左右镜像翻转
# 汇报思路：原型阶段电脑端解耦运行 YOLO，未来量产落地到轻量硬件上同理无缝替换套用 FOMO 模型。
# ==========================================
# 阿尔茨海默症长者“记忆回音药盒”视觉识别原型 V3.2
# ==========================================
# 信号链：
# 1. PillDetector 视觉类：提取固定药盒 ROI 中药丸的颜色特征和数量（为接入 YOLO/FOMO 深度学习解耦）。
# 2. MedicationTracker 业务逻辑类：集成双向时间窗口判定、时段正确性拦截（防错药）、处方剂量校验。
# 3. Pillow 图像高级渲染：抗锯齿中文微软雅黑字体，半透明圆角玻璃态信息卡片，LED 发光光晕呼吸灯。
#
# 交互测试快捷键说明：
# - 按 r/g/b 键：循环设置模拟器“早上/中午/晚上”药格内的药丸数量 (0 -> 1 -> 2 -> 3 -> 0)
# - 按 t 键：循环切换当前系统服药时间段 (Morning -> Noon -> Evening -> Morning)
# - 按 h/s/i 键：模拟 Edge Impulse 标签 hand_to_mouth / swallow / idle
# - 按 q 键：退出程序

COLOR_RANGES = {
    "Morning": [
        (np.array([0, 100, 90]), np.array([10, 255, 255])),
        (np.array([170, 100, 90]), np.array([180, 255, 255])),
        # 白色/米色药丸：低饱和度、高明度
        (np.array([0, 0, 150]), np.array([180, 70, 255])),
    ],
    "Noon": [
        (np.array([35, 70, 70]), np.array([85, 255, 255])),
        # 白色/米色药丸：低饱和度、高明度
        (np.array([0, 0, 150]), np.array([180, 70, 255])),
    ],
    "Evening": [
        (np.array([90, 70, 70]), np.array([130, 255, 255])),
        # 白色/米色药丸：低饱和度、高明度
        (np.array([0, 0, 150]), np.array([180, 70, 255])),
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

ACTION_LABELS = {
    "idle": {
        "name": "IDLE",
        "cn": "空闲",
        "color": (180, 180, 180),
    },
    "hand_to_mouth": {
        "name": "HAND_TO_MOUTH",
        "cn": "手部送药入口",
        "color": (60, 210, 255),
    },
    "swallow": {
        "name": "SWALLOW",
        "cn": "喝水吞咽",
        "color": (80, 240, 120),
    },
}

WINDOW_NAME = "Memory Echo Pillbox - Vision Prototype V3.2"
PRESENT_RATIO_THRESHOLD = 0.075
WARNING_DELAY = 5.0
SWALLOW_ON_TIME_LIMIT = 4.5
CRITICAL_DELAY = WARNING_DELAY * 2

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

    def build_color_mask(self, hsv_roi, color_ranges):
        mask = np.zeros(hsv_roi.shape[:2], dtype=np.uint8)
        for lower, upper in color_ranges:
            mask = cv2.bitwise_or(mask, cv2.inRange(hsv_roi, lower, upper))

        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    def detect(self, frame, slot_key) -> SlotVisionResult:
        config = SLOTS_CONFIG[slot_key]
        x1, y1, x2, y2, cx, cy, radius = slot_geometry(frame.shape, config)
        roi = frame[y1:y2, x1:x2]
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = self.build_color_mask(hsv_roi, self.color_ranges[slot_key])

        circle_mask = np.zeros(mask.shape, dtype=np.uint8)
        cv2.circle(circle_mask, (cx - x1, cy - y1), radius - 4, 255, -1)
        mask = cv2.bitwise_and(mask, circle_mask)

        colored_pixels = cv2.countNonZero(mask)
        total_pixels = max(1, cv2.countNonZero(circle_mask))
        color_ratio = colored_pixels / total_pixels

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = [c for c in contours if cv2.contourArea(c) > total_pixels * 0.012]

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


class MedicationTracker:
    """核心业务逻辑类：管理防错药时段拦截、处方用量校验、双向时间窗口吞咽确认以及虚拟硬件联动状态"""
    def __init__(self, slot_keys):
        self.previous_present = {key: True for key in slot_keys}
        self.pending_since = {key: None for key in slot_keys}
        self.confirmed = {key: False for key in slot_keys}
        self.feedback = {
            key: SlotFeedback("ready", "READY", (100, 255, 100)) for key in slot_keys
        }
        self.last_status = {key: "ready" for key in slot_keys}
        self.streak_count = 0
        self.slow_swallow_count = 0
        
        # V3.0 双向时间窗口与用量校验所增加的参数
        self.last_swallow_time = 0.0
        self.last_consumed_swallow = {key: 0.0 for key in slot_keys}
        self.last_pill_count = {key: 0 for key in slot_keys}
        
        # V3.2 错药即刻报警与帧对比参数
        self.wrong_period_alarm = {key: False for key in slot_keys}
        self.last_frame_pill_count = {key: 0 for key in slot_keys}
        self.last_period = CURRENT_PERIOD
        
        # V3.0 虚拟硬件联动看板的状态
        self.led_status = "OFF"
        self.buzzer_status = "OFF"
        self.voice_status = "OFF"
        self.last_events = []

    def update(self, vision_results, action_label, now=None):
        global CURRENT_PERIOD
        now = time.monotonic() if now is None else now
        events = []
        
        # 如果服药时段切换，重置所有错药报警，避免跨时段残留
        if CURRENT_PERIOD != self.last_period:
            for k in self.wrong_period_alarm:
                self.wrong_period_alarm[k] = False
            self.last_period = CURRENT_PERIOD
        
        # 识别最近一次吞咽时间
        if action_label == "swallow":
            self.last_swallow_time = now
        swallowed_now = (action_label == "swallow")

        for key, result in vision_results.items():
            became_empty = self.previous_present[key] and not result.present
            status_event_emitted = False

            # 判断是否从药盒中拿取了药物：当前帧药丸数少于上一帧，且上一帧有药
            pill_decreased = (self.last_frame_pill_count[key] > 0 and result.pill_count < self.last_frame_pill_count[key])

            if key != CURRENT_PERIOD:
                # 1. 拿错时间段逻辑拦截：只要药丸数减少或者变空，立刻拉响警报
                if pill_decreased or became_empty:
                    if not self.wrong_period_alarm[key]:
                        self.wrong_period_alarm[key] = True
                        events.append(f"[CRITICAL] 警告：在错误时间段拿药！当前为 {CURRENT_PERIOD} 时段，请勿服用 {SLOTS_CONFIG[key]['cn']} 药格的药物！")
                        status_event_emitted = True
                
                # 如果放回了药丸（当前药量恢复到 expected_count 以上），消除错药警报
                expected = MEDICATION_PLAN[key]["expected_count"]
                if result.present and result.pill_count >= expected:
                    if self.wrong_period_alarm[key]:
                        self.wrong_period_alarm[key] = False
                        events.append(f"[INFO] {SLOTS_CONFIG[key]['cn']} 药格错药警报消除：药丸已放回。")
                        status_event_emitted = True

                # 根据报警状态映射反馈
                if self.wrong_period_alarm[key]:
                    feedback = SlotFeedback("critical", f"WRONG PERIOD! (CURRENT: {CURRENT_PERIOD})", (40, 40, 255))
                else:
                    if result.present:
                        self.last_pill_count[key] = result.pill_count  # 暂存当前药丸数
                        if result.pill_count == expected:
                            feedback = SlotFeedback("ready", f"FULL / Pills: {result.pill_count}", (100, 255, 100))
                        else:
                            feedback = SlotFeedback("wrong_ready", f"WRONG DOSAGE ({result.pill_count}/{expected})", (0, 102, 255))
                    else:
                        # 正常空置状态：在非当前时段且无报警，显示中性的“空置就绪”
                        feedback = SlotFeedback("empty_normal", "EMPTY / READY", (180, 180, 180))
            else:
                # 2. 拿对时间段逻辑
                self.wrong_period_alarm[key] = False
                
                if result.present:
                    # 重新装药，复位此药格所有状态
                    self.pending_since[key] = None
                    self.confirmed[key] = False
                    self.last_pill_count[key] = result.pill_count  # 暂存当前药丸数作为服药对比
                    
                    expected = MEDICATION_PLAN[key]["expected_count"]
                    if result.pill_count == expected:
                        feedback = SlotFeedback("ready", f"FULL / Pills: {result.pill_count}", (100, 255, 100))
                    else:
                        feedback = SlotFeedback("wrong_ready", f"WRONG DOSAGE ({result.pill_count}/{expected})", (0, 102, 255))
                else:
                    # 药盒变空逻辑
                    if became_empty:
                        # 检查“变空前窗口 (5.0s)”是否有未消费的吞咽动作
                        if self.last_swallow_time > self.last_consumed_swallow[key] and (now - self.last_swallow_time <= 5.0):
                            self.confirmed[key] = True
                            self.pending_since[key] = None
                            self.last_consumed_swallow[key] = self.last_swallow_time
                            
                            actual_taken = self.last_pill_count[key]
                            expected = MEDICATION_PLAN[key]["expected_count"]
                            
                            if actual_taken == expected:
                                feedback = SlotFeedback("confirmed", "CONFIRMED: TAKEN", (80, 240, 120))
                                self.streak_count += 1
                                self.slow_swallow_count = 0
                                swallow_duration = now - self.last_swallow_time
                                events.append(
                                    self._format_event(
                                        key,
                                        "confirmed_early",
                                        swallow_duration=swallow_duration,
                                        streak_count=self.streak_count,
                                    )
                                )
                                if self.streak_count % 3 == 0:
                                    events.append(self._format_event(key, "reward", streak_count=self.streak_count))
                            else:
                                feedback = SlotFeedback("warning", f"DOSAGE ERROR: TAKEN {actual_taken}", (0, 102, 255))
                                self.streak_count = 0
                                events.append(f"[WARNING] 服药数量异常！预期 {expected} 颗，视觉检出 {actual_taken} 颗。")
                            status_event_emitted = True
                        else:
                            self.pending_since[key] = now
                            feedback = SlotFeedback("waiting", "WAITING SWALLOW", (60, 220, 255))

                    if self.confirmed[key]:
                        actual_taken = self.last_pill_count[key]
                        expected = MEDICATION_PLAN[key]["expected_count"]
                        if actual_taken == expected:
                            feedback = SlotFeedback("confirmed", "CONFIRMED: TAKEN", (80, 240, 120))
                        else:
                            feedback = SlotFeedback("warning", f"DOSAGE ERROR: TAKEN {actual_taken}", (0, 102, 255))
                    else:
                        # 尚未确认，检查“变空后窗口”是否检测到吞咽动作
                        if became_empty:
                            pass
                        elif swallowed_now and self.pending_since[key] is not None:
                            swallow_duration = now - self.pending_since[key]
                            self.confirmed[key] = True
                            self.pending_since[key] = None
                            self.last_consumed_swallow[key] = self.last_swallow_time
                            
                            actual_taken = self.last_pill_count[key]
                            expected = MEDICATION_PLAN[key]["expected_count"]
                            
                            if actual_taken == expected:
                                feedback = SlotFeedback("confirmed", "CONFIRMED: TAKEN", (80, 240, 120))
                                if swallow_duration <= SWALLOW_ON_TIME_LIMIT:
                                    self.streak_count += 1
                                    self.slow_swallow_count = 0
                                    events.append(
                                        self._format_event(
                                            key,
                                            "confirmed",
                                            swallow_duration=swallow_duration,
                                            streak_count=self.streak_count,
                                        )
                                    )
                                    if self.streak_count % 3 == 0:
                                        events.append(self._format_event(key, "reward", streak_count=self.streak_count))
                                else:
                                    self.streak_count = 0
                                    self.slow_swallow_count += 1
                                    events.append(self._format_event(key, "confirmed_slow", swallow_duration=swallow_duration))
                                    if self.slow_swallow_count >= 2:
                                        events.append(
                                            self._format_event(
                                                key,
                                                "medical",
                                                swallow_duration=swallow_duration,
                                                slow_count=self.slow_swallow_count,
                                            )
                                        )
                            else:
                                feedback = SlotFeedback("warning", f"DOSAGE ERROR: TAKEN {actual_taken}", (0, 102, 255))
                                self.streak_count = 0
                                events.append(f"[WARNING] 服药数量异常！预期 {expected} 颗，视觉检出 {actual_taken} 颗。")
                            status_event_emitted = True
                        else:
                            # 没检测到吞咽，根据超时状态变色
                            wait_time = 0.0 if self.pending_since[key] is None else now - self.pending_since[key]
                            if wait_time >= CRITICAL_DELAY:
                                self.streak_count = 0
                                feedback = SlotFeedback("critical", "CRITICAL: FAKE TAKING?", (40, 40, 255))
                            elif wait_time >= WARNING_DELAY:
                                self.streak_count = 0
                                feedback = SlotFeedback("warning", "WARNING: NO SWALLOW", (60, 220, 255))
                            else:
                                feedback = SlotFeedback("waiting", "WAITING SWALLOW", (60, 220, 255))

            if feedback.status != self.last_status[key]:
                if not status_event_emitted:
                    events.append(self._format_event(key, feedback.status))
                self.last_status[key] = feedback.status

            self.feedback[key] = feedback
            self.last_frame_pill_count[key] = result.pill_count
            self.previous_present[key] = result.present

        # 吞咽动作与药量关联校验：如果吞咽动作发生，但当前服药药格依然有药，说明发生了逻辑断层
        if swallowed_now:
            active_result = vision_results[CURRENT_PERIOD]
            if active_result.present:
                events.append(f"[WARNING] 检测到吞咽动作，但当前药格 {SLOTS_CONFIG[CURRENT_PERIOD]['cn']} 药丸未减少，提示漏服或假吃风险！")

        self.last_events = events
        self.update_hardware_state(now)
        return self.feedback, events

    def update_hardware_state(self, now):
        """根据当前药格与日志状态，计算声光报警器的模拟输出指标"""
        self.led_status = "OFF"
        self.buzzer_status = "OFF"
        self.voice_status = "OFF"

        has_critical = any(fb.status == "critical" for fb in self.feedback.values()) or any(self.wrong_period_alarm.values())
        
        has_warning_dosage = False
        for key, fb in self.feedback.items():
            if fb.status == "warning" and "DOSAGE ERROR" in fb.text:
                has_warning_dosage = True
                
        has_confirmed = any(fb.status == "confirmed" for fb in self.feedback.values())
        has_waiting = any(fb.status in ("waiting", "warning") for fb in self.feedback.values())

        if has_critical:
            self.led_status = "RED"
            self.buzzer_status = "ALARM"
            # 优先提示拿错时段
            if any(self.wrong_period_alarm.values()) or any("拿错" in str(evt) or "错误时间段" in str(evt) for evt in self.last_events):
                self.voice_status = "WRONG_SLOT"
            else:
                self.voice_status = "URGENT_CONFIRM"
        elif has_warning_dosage:
            self.led_status = "RED"
            self.buzzer_status = "ALARM"
            self.voice_status = "DOSAGE_ERROR"
        elif has_confirmed:
            self.led_status = "GREEN"
            self.buzzer_status = "SHORT_BEEP"
            self.voice_status = "NORMAL_CONFIRMED"
        elif has_waiting:
            self.led_status = "YELLOW"
            self.buzzer_status = "OFF"
            self.voice_status = "OFF"

        # 吞咽动作发生但药未变警告（在无高级警报时触发）
        if self.voice_status == "OFF" and any("药丸未减少" in str(evt) for evt in self.last_events):
            self.led_status = "YELLOW"
            self.voice_status = "SWALLOW_BUT_FULL"


    @staticmethod
    def _format_event(slot_key, status, **details):
        cn_name = SLOTS_CONFIG[slot_key]["cn"]

        if status == "confirmed":
            duration = details.get("swallow_duration", 0.0)
            streak = details.get("streak_count", 0)
            return (
                f"[INFO] {cn_name}服药已确认：吞咽耗时 {duration:.1f}s，"
                f"连续打卡 {streak} 次；仅记录无感打卡。"
            )
        if status == "confirmed_early":
            duration = details.get("swallow_duration", 0.0)
            streak = details.get("streak_count", 0)
            return (
                f"[INFO] {cn_name}服药已确认（提前吞咽）：吞咽动作发生在药格变空前 {duration:.1f}s，"
                f"连续打卡 {streak} 次；仅记录无感打卡。"
            )
        if status == "confirmed_slow":
            duration = details.get("swallow_duration", 0.0)
            return (
                f"[INFO] {cn_name}服药已确认，但吞咽耗时 {duration:.1f}s，"
                "本次不计入连续打卡。"
            )
        if status == "waiting":
            return f"[INFO] {cn_name}药格变空：等待吞咽动作确认。"
        if status == "warning":
            return f"[WARNING] {cn_name}药格已空但未及时检测到吞咽：触发本地语音温和催促。"
        if status == "critical":
            return f"[CRITICAL] {cn_name}长时间未检测到吞咽：疑似假吃/漏服，建议通知家属确认。"
        if status == "reward":
            streak = details.get("streak_count", 0)
            return f"[REWARD] 连续按时服药 {streak} 次：解锁亲情照片盲盒奖励。"
        if status == "medical":
            duration = details.get("swallow_duration", 0.0)
            slow_count = details.get("slow_count", 0)
            return (
                f"[MEDICAL] 连续 {slow_count} 次吞咽耗时超过 {SWALLOW_ON_TIME_LIMIT:.1f}s；"
                f"本次 {cn_name}吞咽耗时 {duration:.1f}s，提示吞咽变慢风险。"
            )
        if status == "ready":
            return f"[INFO] {cn_name}药格检测到药丸/托盘：状态复位为未服药。"
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

def draw_top_banner_pil(draw, tracker, action_label):
    """绘制精美的系统顶部状态卡片栏"""
    font_title = get_font(15, bold=True)
    font_sub = get_font(10)
    font_info = get_font(11, bold=True)
    
    # 绘制深底板
    draw.rectangle([0, 0, 900, 64], fill=(20, 24, 30, 255))
    draw.line([0, 64, 900, 64], fill=(80, 85, 95, 255), width=1)
    
    # 左侧系统名称
    draw.text((20, 13), "记忆回音 · 阿尔茨海默症辅助服药系统 V3.2", font=font_title, fill=(255, 255, 255, 255))
    draw.text((20, 36), "Memory Echo Smart Pillbox Monitor", font=font_sub, fill=(150, 155, 165, 255))
    
    # 右侧动作监测状态与连续打卡天数
    action_info = ACTION_LABELS[action_label]
    act_str = f"动作检测: 【{action_info['cn']}】"
    act_color = action_info['color']
    act_color_rgb = (act_color[2], act_color[1], act_color[0], 255)  # BGR 转换为 RGBA
    
    draw.text((900 - 450, 22), act_str, font=font_info, fill=act_color_rgb)
    
    if tracker is not None:
        streak_str = f"连续按时服药打卡: {tracker.streak_count} 次"
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
            badge_str = "药格变空 · 等待吞咽"
        elif status == "warning":
            if "DOSAGE ERROR" in status_text:
                border_color = (255, 100, 0)  # 橙色
                badge_bg = (230, 80, 10, 255)
                badge_str = "服药数量异常！"
            else:
                border_color = (255, 210, 0)  # 黄色
                badge_bg = (210, 170, 0, 255)
                badge_text_color = (30, 30, 30, 255)
                badge_str = "未检测到吞咽 · 语音催促"
        elif status == "confirmed":
            border_color = (80, 240, 120)  # 绿色
            badge_bg = (40, 180, 80, 255)
            badge_str = "正常服药已确认"
        elif status == "critical":
            border_color = (255, 40, 40)   # 红色
            badge_bg = (220, 30, 30, 255)
            if "WRONG PERIOD" in status_text:
                badge_str = "警告：拿错时间段！"
            else:
                badge_str = "严重警告：疑似假吃！"
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
            info_str = f"处方: {expected} 粒  |  当前: {actual} 粒"
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

    font_title = get_font(12, bold=True)
    font_text = get_font(11)
    font_voice = get_font(11, bold=True)

    # 1. 绘制半透明磨砂效果面板背景（半透明深色填充 + 极细白色高光描边）
    draw.rounded_rectangle([panel_x1, panel_y1, panel_x2, panel_y2], radius=12, fill=(24, 28, 36, 170), outline=(255, 255, 255, 40), width=1)
    
    # 2. 内圈白色软微光描边，提升卡片边缘的通透感
    draw.rounded_rectangle([panel_x1 + 1, panel_y1 + 1, panel_x2 - 1, panel_y2 - 1], radius=11, fill=None, outline=(255, 255, 255, 25), width=1)
    
    # 看板标题
    draw.text((panel_x1 + 15, panel_y1 + 8), f"【设备硬件联动仿真】(当前核对: {SLOTS_CONFIG[CURRENT_PERIOD]['cn']})", font=font_title, fill=(230, 230, 230, 255))
    
    # 计算 LED 灯中心位置
    cx_led, cy_led = panel_x1 + 35, panel_y1 + 44
    r_led = 9
    
    # 渲染 LED 模拟指示灯光晕
    if tracker.led_status == "GREEN":
        draw_glow_led(draw, cx_led, cy_led, r_led, (80, 240, 120, 255), (40, 120, 60, 140), (20, 60, 30, 60))
        led_text = "正常服药确认 (GREEN)"
        led_text_color = (80, 240, 120, 255)
    elif tracker.led_status == "YELLOW":
        draw_glow_led(draw, cx_led, cy_led, r_led, (255, 210, 0, 255), (130, 105, 0, 140), (65, 50, 0, 60))
        led_text = "药格变空待吞咽 (YELLOW)"
        led_text_color = (255, 210, 0, 255)
    elif tracker.led_status == "RED":
        if int(time.time() * 2) % 2 == 0:
            draw_glow_led(draw, cx_led, cy_led, r_led, (255, 40, 40, 255), (130, 20, 20, 140), (65, 10, 10, 60))
            led_text = "警报闪烁中 (RED)"
        else:
            draw_glow_led(draw, cx_led, cy_led, r_led, (80, 20, 20, 255), (40, 10, 10, 100), (30, 5, 5, 50))
            led_text = "警报闪烁中 (OFF)"
        led_text_color = (255, 40, 40, 255)
    else:
        draw_glow_led(draw, cx_led, cy_led, r_led, (100, 100, 100, 255), (60, 60, 60, 100), (40, 40, 40, 50))
        led_text = "待机就绪 (OFF)"
        led_text_color = (160, 165, 175, 255)
        
    draw.text((panel_x1 + 58, panel_y1 + 38), f"LED 指示灯: {led_text}", font=font_text, fill=led_text_color)
    
    # 模拟蜂鸣器输出
    buzzer_text_color = (180, 185, 195, 255)
    buzzer_text = "静音"
    if tracker.buzzer_status == "SHORT_BEEP":
        buzzer_text = "短鸣“滴~” (服药确认)"
        buzzer_text_color = (80, 240, 120, 255)
    elif tracker.buzzer_status == "ALARM":
        if int(time.time() * 4) % 2 == 0:
            buzzer_text = "持续警报“哔! 哔! 哔!”"
            buzzer_text_color = (255, 40, 40, 255)
        else:
            buzzer_text = "持续警报 (间歇)"
            buzzer_text_color = (130, 20, 20, 255)
            
    draw.text((panel_x1 + 15, panel_y1 + 64), f"模拟蜂鸣器: {buzzer_text}", font=font_text, fill=buzzer_text_color)
    
    # 模拟语音 TTS 播报
    voice_text = "静音"
    voice_color = (160, 165, 175, 255)
    if tracker.voice_status == "NORMAL_CONFIRMED":
        voice_text = "“服药已确认，打卡成功！”"
        voice_color = (80, 240, 120, 255)
    elif tracker.voice_status == "DOSAGE_ERROR":
        voice_text = "“剂量错误，请核对药量！”"
        voice_color = (255, 140, 0, 255)
    elif tracker.voice_status == "WRONG_SLOT":
        voice_text = f"“拿错药格，当前为{SLOTS_CONFIG[CURRENT_PERIOD]['cn']}时段！”"
        voice_color = (255, 40, 40, 255)
    elif tracker.voice_status == "URGENT_CONFIRM":
        voice_text = "“请尽快服药并完成吞咽！”"
        voice_color = (255, 210, 0, 255)
    elif tracker.voice_status == "SWALLOW_BUT_FULL":
        voice_text = "“检测到吞咽动作，但药量未减，请确认！”"
        voice_color = (255, 140, 0, 255)
        
    draw.text((panel_x1 + 15, panel_y1 + 90), "语音播报文本:", font=font_text, fill=(200, 205, 215, 255))
    draw.text((panel_x1 + 105, panel_y1 + 90), voice_text, font=font_voice, fill=voice_color)


def process_frame(frame, action_label="idle", tracker=None, detector=None):
    if detector is None:
        detector = PillDetector()
    output = frame.copy()
    
    # 1. 视觉检测提取
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
        feedback, events = tracker.update(vision_results, action_label)

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
    draw_top_banner_pil(ImageDraw.Draw(img_base), tracker, action_label)
    
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


def draw_simulator_scene(slot_states, action_label):
    img = np.full((560, 900, 3), (42, 45, 48), dtype=np.uint8)

    # 绘制药盒主体大边框
    cv2.rectangle(img, (70, 210), (830, 440), (62, 65, 68), -1)
    cv2.rectangle(img, (70, 210), (830, 440), (122, 126, 130), 2)
    
    # 底部按键操作说明提示
    cv2.putText(img, "SIMULATOR: r/g/b cycle count (0-3), t cycle period, h hand, s swallow, i idle, q quit",
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

    draw_person_and_action(img, action_label)
    return img


def draw_person_and_action(img, action_label):
    """绘制右侧被监护人简易画像和行为动效"""
    face_center = (690, 125)
    mouth = (690, 148)
    cv2.circle(img, face_center, 52, (205, 185, 165), -1, lineType=cv2.LINE_AA)
    cv2.circle(img, (670, 110), 5, (40, 40, 40), -1, lineType=cv2.LINE_AA)
    cv2.circle(img, (710, 110), 5, (40, 40, 40), -1, lineType=cv2.LINE_AA)
    cv2.ellipse(img, mouth, (20, 8), 0, 0, 180, (60, 60, 60), 2, lineType=cv2.LINE_AA)
    cv2.line(img, (690, 177), (690, 205), (190, 170, 150), 8, lineType=cv2.LINE_AA)

    if action_label == "hand_to_mouth":
        cv2.line(img, (560, 225), (635, 170), (185, 160, 140), 14, lineType=cv2.LINE_AA)
        cv2.circle(img, (645, 164), 18, (205, 185, 165), -1, lineType=cv2.LINE_AA)
        cv2.circle(img, (666, 152), 8, (245, 245, 245), -1, lineType=cv2.LINE_AA)
    elif action_label == "swallow":
        cv2.rectangle(img, (598, 138), (626, 183), (220, 235, 245), -1)
        cv2.rectangle(img, (598, 138), (626, 183), (150, 170, 185), 2)
        cv2.line(img, (632, 160), (660, 150), (185, 160, 140), 10, lineType=cv2.LINE_AA)
        cv2.circle(img, (690, 190), 11, (80, 240, 120), 2, lineType=cv2.LINE_AA)
        cv2.circle(img, (690, 190), 20, (80, 240, 120), 1, lineType=cv2.LINE_AA)


def print_intro(use_camera):
    print("==================================================")
    print(" 阿尔茨海默症长者“记忆回音药盒”视觉识别原型 V3.2")
    print("==================================================")
    print("视觉任务：药格空置与数量核对 + 服药动作分类 + 时间段与剂量校验")
    print("按键说明：")
    print("  r     : 循环切换“早上(Morning)”药格药片数 (0->1->2->3->0)")
    print("  g     : 循环切换“中午(Noon)”药格药片数")
    print("  b     : 循环切换“晚上(Evening)”药格药片数")
    print("  t     : 循环切换当前系统服药时间段 (Morning->Noon->Evening->Morning)")
    print("  h     : 模拟 Edge Impulse 标签 hand_to_mouth（手部送药入口）")
    print("  s     : 模拟 Edge Impulse 标签 swallow（喝水吞咽）")
    print("  i     : 模拟 Edge Impulse 标签 idle（空闲）")
    print("  q     : 退出程序")
    print("模式：", "摄像头识别 + 键盘动作模拟" if use_camera else "无摄像头模拟器")
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


def handle_keypress(key, slot_states, current_action):
    global CURRENT_PERIOD
    if key == ord("q"):
        return current_action, True
    
    if key == ord("r"):
        slot_states["Morning"] = (slot_states["Morning"] + 1) % 4
        print(f"模拟器更新：早上药格内药片数量循环设为 {slot_states['Morning']}")
    elif key == ord("g"):
        slot_states["Noon"] = (slot_states["Noon"] + 1) % 4
        print(f"模拟器更新：中午药格内药片数量循环设为 {slot_states['Noon']}")
    elif key == ord("b"):
        slot_states["Evening"] = (slot_states["Evening"] + 1) % 4
        print(f"模拟器更新：晚上药格内药片数量循环设为 {slot_states['Evening']}")
        
    elif key == ord("t"):
        if CURRENT_PERIOD == "Morning":
            CURRENT_PERIOD = "Noon"
        elif CURRENT_PERIOD == "Noon":
            CURRENT_PERIOD = "Evening"
        else:
            CURRENT_PERIOD = "Morning"
        print(f"模拟器更新：当前系统时段切换为【{CURRENT_PERIOD}】")
        
    elif key == ord("h"):
        current_action = "hand_to_mouth"
        slot_states[CURRENT_PERIOD] = 0  # 自动将当前时段药盒清空
        print(f"动作分类模拟：手部送药入口。当前时段【{CURRENT_PERIOD}】药格自动清空！")
    elif key == ord("s"):
        current_action = "swallow"
        slot_states[CURRENT_PERIOD] = 0  # 自动将当前时段药盒清空
        print(f"动作分类模拟：喝水吞咽。当前时段【{CURRENT_PERIOD}】药格已清空！")
    elif key == ord("i"):
        current_action = "idle"
        print("动作分类模拟：空闲")
    return current_action, False


def save_demo_snapshot(path):
    """保存一张模拟器识别结果的精美截图"""
    global CURRENT_PERIOD
    CURRENT_PERIOD = "Morning"
    # 早上放2颗，中午放1颗，晚上放3颗。然后晚上拿走1颗触发拿错药警报！
    slot_states = {"Morning": 2, "Noon": 1, "Evening": 3}
    tracker = MedicationTracker(SLOTS_CONFIG.keys())
    detector = PillDetector()
    
    # 首先更新一帧，记录初始装药量（3颗）
    frame_init = draw_simulator_scene(slot_states, "idle")
    tracker.update({
        "Morning": SlotVisionResult(True, 1.0, 0.1, (0,0,10,10), 2),
        "Noon": SlotVisionResult(True, 1.0, 0.1, (0,0,10,10), 1),
        "Evening": SlotVisionResult(True, 1.0, 0.1, (0,0,10,10), 3)
    }, "idle")
    
    # 模拟拿走一颗药
    slot_states["Evening"] = 2
    frame = draw_simulator_scene(slot_states, "idle")
    processed, _, _, events = process_frame(frame, "idle", tracker, detector)
    
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), processed)
    for event in events:
        print("EVENT:", event)
    print(f"已保存演示截图：{path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Memory Echo Pillbox OpenCV prototype V3.2")
    parser.add_argument("--camera-index", type=int, default=0, help="摄像头编号，默认 0")
    parser.add_argument(
        "--camera-backend",
        choices=("auto", "dshow", "msmf", "default"),
        default="auto",
        help="摄像头后端：Windows 推荐 auto/dshow；MSMF 报错时可显式使用 dshow",
    )
    parser.add_argument("--no-camera", action="store_true", help="强制使用模拟器")
    parser.add_argument("--snapshot", type=str, help="保存一张模拟器识别结果截图后退出")
    return parser.parse_args()


def main():
    global CURRENT_PERIOD
    args = parse_args()

    if args.snapshot:
        save_demo_snapshot(args.snapshot)
        return

    # 早上默认有2粒（正确用量），中午1粒（正确），晚上3粒（正确）
    slot_states = {"Morning": 2, "Noon": 1, "Evening": 3}
    tracker = MedicationTracker(SLOTS_CONFIG.keys())
    detector = PillDetector()
    current_action = "idle"

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
            cv2.flip(frame, 1, frame)
        else:
            frame = draw_simulator_scene(slot_states, current_action)

        processed, _, _, events = process_frame(frame, current_action, tracker, detector)
        for event in events:
            print("反馈事件：", event)

        cv2.imshow(WINDOW_NAME, processed)
        key = cv2.waitKey(30) & 0xFF
        current_action, should_quit = handle_keypress(key, slot_states, current_action)
        if should_quit:
            break

    if cap is not None and cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()
    print("程序已安全退出。")


if __name__ == "__main__":
    main()
