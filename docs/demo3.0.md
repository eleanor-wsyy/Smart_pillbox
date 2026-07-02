# 角色设定

> Legacy note: 本文件是 V3.0 历史需求草案，里面的吞咽确认、动作模拟和 `swallow_duration` 逻辑已经被 V4.0 废弃。当前交付版本以 `docs/v4_yolo_opencv_hybrid_upgrade.md` 和 `docs/v4_flowchart_mermaid.md` 为准：系统只基于 `pill_count` 的稳定下降生成取药事件。

你是一位资深的 Python 架构师与计算机视觉专家。请基于我已经跑通的 `smart_pillbox_opencv2.0.py` 代码，进行 V3.0 版本的核心业务逻辑升级与架构重构。

# 核心目标
在保持现有 UI 渲染与数据结构（`SlotVisionResult`, `SlotFeedback`）的基础上，引入“防错药机制”、“处方数量核对”，并将现有的传统 OpenCV 颜色识别重构为支持接入深度学习目标检测模型（如 YOLO / Edge Impulse FOMO）的面向对象架构。

---

## 需求模块一：业务逻辑层升级 (`MedicationTracker` 类扩充)

### 1. 引入当前时间上下文与防错药警报 (Wrong Slot Alert)
- 设定一个模拟的当前时间段全局变量，例如 `CURRENT_PERIOD = "Morning"`。
- **逻辑设计**：在 `update` 方法中，若系统检测到非当前时段的药格（如 "Noon" 或 "Evening"）变空（`became_empty`），必须立刻拦截正常的确认流程，触发反馈状态为 `"critical"`。
- **事件输出**：追加生成日志 `[CRITICAL] 警告：拿错时间段药物！当前为 Morning，请勿服用 Noon 药格！`

### 2. 引入轻量级处方数据库与数量核对 (Medication Plan Check)
- 新增全局配置字典 `MEDICATION_PLAN`，格式如下：`{"Morning": {"expected_count": 2}, "Noon": {"expected_count": 1}, "Evening": {"expected_count": 3}}`。
- **逻辑设计**：当正确时段的药格变空，且确认 `swallow` 动作后，立刻比对视觉识别出的 `pill_count`（记录在变成空之前的最后一次有效识别中，或直接简化比对逻辑）与 `MEDICATION_PLAN` 中的 `expected_count`。
- **事件输出**：若数量不符（漏吃/多吃），覆盖原有状态，触发 `"warning"`，并输出日志 `[WARNING] 服药数量异常！预期 X 颗，视觉检出 Y 颗。`；若数量完全匹配，则走原有的 `[INFO]` 和 `[REWARD]` 流程。

---

## 需求模块二：视觉架构重构 (面向深度学习模型演进)

目前的药丸计数强依赖 `COLOR_RANGES` 和 `cv2.findContours`。为了后续能平滑切换到 YOLO 或 Edge Impulse FOMO 模型，我们需要对代码解耦。

### 1. 封装 `PillDetector` 类
- 请移除原本零散的 `build_color_mask` 和 `detect_slot_presence` 函数。
- 新建一个 `PillDetector` 类。包含初始化方法和 `detect(frame, slot_key)` 方法。
- 在 `detect` 方法内部，暂时保留原有的 HSV 提取和轮廓计数逻辑（作为 YOLO 模型训练好之前的 Mock 占位符），并返回现有的 `SlotVisionResult` 对象。
- **目的**：通过将视觉检测逻辑全部收拢到 `PillDetector` 类的 `detect` 方法中，确保 `process_frame` 和主循环不用关心底层是 OpenCV 还是 YOLO。

---

## 🚫 严格约束条件
1. **绝对保持** 原有的模拟器绘图功能 (`draw_simulator_scene`, `draw_person_and_action`)、UI 渲染逻辑 (`draw_slot_overlay`) 以及按键拦截逻辑 (`handle_keypress`) 不变，确保我的 Demo 可视化不被破坏。
2. 保持原有的 Streak 连续打卡和 `swallow_duration` 吞咽困难医学预警逻辑正常运转。
3. 请为新增的逻辑和类添加清晰的中文注释。为节省 Token，你可以省略未修改的大块 UI 函数代码。
