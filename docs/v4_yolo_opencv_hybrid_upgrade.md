# Smart Pillbox V4.0 Detection Stabilization Plan

## No Swallow / Pill Count Only Version

本版本根据小组讨论移除所有虚假的行为识别和吞咽确认逻辑。系统不再声称能用单摄像头判断“是否吞咽”，而是聚焦更可靠、可落地的任务：

```text
Roboflow / YOLO = 药丸视觉检测
OpenCV ROI = 药格空间映射
Temporal Smoothing = pill_count 时间稳定
Event Debounce = 连续下降确认 -> 取药事件
Safety State Machine = 正确取药 / 错格 / 剂量异常 / 漏服提醒
```

---

## 1. Remove Completely

请移除或禁用以下模块：

- `hand_to_mouth` 检测
- `swallow` 检测
- `idle / action_label` 分类
- Edge Impulse 手势模拟
- 键盘 `h / s / i` 行为输入
- 任何基于动作序列推断“已经吞咽”的逻辑
- 任何“吞咽确认成功”文案

原因：单摄像头俯拍药盒无法可靠证明老人真的吞咽。保留这部分会让老师质疑方案落地性。

---

## 2. Keep As Core

### Vision Layer

保留：

- Roboflow 云端 YOLO 模型：`pill-detection-fnftd/3`
- 本地 YOLO 可选接入
- OpenCV fallback 模拟检测
- `SlotVisionResult`
- `pill_count`
- bbox / class / confidence / class_counts

### Slot Mapping

保留：

- Morning / Noon / Evening 三个固定药格
- `center_ratio` 定位
- ROI 空间映射
- bbox 中心点落入药格半径的判断

---

## 3. New Core: Event Generator

系统核心事件只来自药丸数量变化，但不能再使用单帧差值直接触发。新的事件链路是：

```python
stable_count = ema(raw_pill_count)

if baseline_count - stable_count >= 1:
    confirm_frames += 1
else:
    confirm_frames = 0

if confirm_frames >= 2:
    taken_count = baseline_count - stable_count
    generate_event("TAKE_MED_EVENT")
```

行为定义：

- `TAKE_MED_EVENT` 必须满足 `pill_count` 连续下降，且同一下降结果持续至少 2 帧。
- `MISSED_RISK` 表示当前时段超过提醒时间仍没有已确认取药事件。
- `WRONG_SLOT` 表示非当前时间段药格发生已确认取药事件。
- `UNCERTAIN` 表示检测置信度过低时暂停成功/失败判定，不写入成功记录。

事件字段建议：

```python
{
    "type": "TAKE_MED_EVENT",
    "slot": "Morning",
    "previous_count": 2,
    "current_count": 0,
    "taken_count": 2,
    "timestamp": now,
    "confidence": 0.93,
}
```

---

## 4. State Machine

```text
MONITORING
  -> NORMAL_SUCCESS
  -> WARNING_DOSAGE
  -> LOCKED_WRONG_SLOT
  -> MISSED_RISK
  -> UNCERTAIN
  -> RECOVERY
```

### State Rules

| State | Trigger | Meaning |
|---|---|---|
| `MONITORING` | 当前无取药事件 | 正常监控 |
| `NORMAL_SUCCESS` | 当前时段正确药格发生取药事件，且取出数量匹配处方 | 正确取药已确认 |
| `WARNING_DOSAGE` | 当前时段正确药格发生取药事件，但取出数量不匹配处方 | 剂量异常 |
| `LOCKED_WRONG_SLOT` | 非当前时段药格发生取药事件 | 错误孔位取药 |
| `MISSED_RISK` | 到服药时间后长时间没有取药事件 | 漏服风险 |
| `UNCERTAIN` | 检测置信度低或画面不可用 | 暂停判定 |
| `RECOVERY` | 错格取药后药丸放回 | 恢复监控 |

---

## 5. Detection Stabilization Fixes

### Temporal Smoothing

`MedicationTracker` 对每个药格维护 EMA 计数：

```python
stable = alpha * current + (1 - alpha) * previous
```

这样可以降低 `pill_count` 在相邻帧之间的随机波动，避免 UI 和状态机频繁跳变。

### Event Debounce

取药事件不再由一帧 `previous > current` 触发。系统维护 `event_baseline_count` 和 `pending_take_event`，只有同一下降结果连续出现至少 2 帧，才确认 `TAKE_MED_EVENT`。

### ROI Stability

OpenCV fallback 检测对 mask 做轻量增强：

```python
mask = cv2.GaussianBlur(mask, (9, 9), 0)
mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
```

圆形 ROI 也使用轻微软边界，减少药丸边缘被硬切造成的误检/漏检。

### Contour Filtering Tuning

轮廓过滤从过低面积阈值升级为：

```python
contourArea > total_pixels * 0.02
0.45 <= aspect_ratio <= 2.2
fill_ratio >= 0.42
```

同时收紧浅色药丸 HSV 范围，降低白色背景和小光斑误识别。

---

## 6. Decision Logic

```python
if confidence < threshold:
    state = "UNCERTAIN"

elif no_take_event and time_window_expired:
    state = "MISSED_RISK"

elif take_event.slot != current_period:
    state = "LOCKED_WRONG_SLOT"

elif take_event.taken_count != medication_plan[current_period].expected_count:
    state = "WARNING_DOSAGE"

else:
    state = "NORMAL_SUCCESS"
```

---

## 7. Output Feedback

系统输出只围绕取药事件和风险：

- 界面状态：绿 / 黄 / 红
- 指示灯：`GREEN` / `YELLOW` / `RED`
- 声音提示：
  - 请按时取药
  - 请核对药量
  - 当前不是该药格服药时间
  - 请调整摄像头画面
- 系统日志
- 家属端通知

---

## 8. Roboflow Usage

当前主方案可以直接使用 Roboflow：

- Model page: https://universe.roboflow.com/pill-detection-cun5i/pill-detection-fnftd/model/3
- Model ID: `pill-detection-fnftd/3`
- Classes: `capsules`, `tablets`

运行：

```powershell
$env:ROBOFLOW_API_KEY="your_api_key"
python smart_pillbox_opencv.py --detector roboflow
```

如果没有 API key，当前代码的 `--detector auto` 会自动回退到本地 OpenCV 模拟检测，方便课堂演示。

---

## 9. Demo Tests

### Test 1: 正常取药

```text
current_period = Morning
Morning pill_count: 2 -> 0
taken_count = 2
expected_count = 2
=> NORMAL_SUCCESS
```

说明：`Morning pill_count: 2 -> 0` 必须连续确认至少 2 帧，才会生成 `TAKE_MED_EVENT`。

### Test 2: 错误孔位

```text
current_period = Morning
Evening pill_count: 3 -> 2
=> LOCKED_WRONG_SLOT
```

说明：错格也必须先形成已确认取药事件，未发生药丸移动时只做温和提醒或继续监控。

### Test 3: 剂量异常

```text
current_period = Morning
Morning pill_count: 3 -> 0
taken_count = 3
expected_count = 2
=> WARNING_DOSAGE
```

### Test 4: 漏服风险

```text
current_period = Morning
time_window_expired = true
no pill_count decrease
=> MISSED_RISK
```

### Test 5: 视觉不确定

```text
confidence < threshold
=> UNCERTAIN
```

---

## 10. Current Problem Coverage

| Problem | Fix |
|---|---|
| pill_count 抖动 | EMA 时间平滑 |
| 单帧误触发 TAKE_EVENT | 连续 2 帧事件防抖 |
| ROI 边缘误差 | mask 高斯平滑 + 软 ROI |
| false positives | 提高 contourArea 阈值 + 形状过滤 |
| 状态机频繁跳变 | 只接受稳定计数和已确认事件 |

---

## 11. Presentation Positioning

答辩推荐说法：

> 我们没有用单摄像头去伪造吞咽识别，而是把系统重构为更可靠的视觉取药事件监控。Roboflow / YOLO 负责药丸检测，OpenCV 负责药格空间映射，状态机根据药丸数量变化判断是否按时、按格、按剂量取药，并在漏服、错格和剂量异常时给出反馈。

