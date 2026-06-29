# 实施计划 - 智能药盒状态复位、双向时间窗口与药量校验警报优化

根据您提供的新讨论记录，我们针对**药片体积小导致数量不易识别、各药格预设用量不同、服药剂量错误警报**等实际痛点，对实施计划进行了进一步升级。

我们将完整合并您组员在 [smart_pillbox_opencv(1)(1).py](file:///d:/interface/smart_pillbox_opencv(1)(1).py) 中的全部工作，并在其基础上实现一个功能更丰富、交互更逼真的系统。

## 用户评审要点

> [!IMPORTANT]
> 1. **药丸数量预设**：为早、中、晚三个药格分别预设所需的标准用量（早上 1 粒，中午 2 粒，晚上 1 粒）。
> 2. **剂量状态校验**：当药格放药后，若数量不等于预设值，UI 会显示橙色警示 `WRONG DOSAGE`；只有数量正确时才显示绿色 `READY`。
> 3. **剂量错误警报**：当老人在药格变空且检测到吞咽后，系统会检查其刚才取走的药丸数量。如果取走数量与预设值不符，将触发 `[ALARM]` 警报，警告服药剂量错误。
> 4. **逼真的多药丸模拟器**：将模拟器升级为支持多药丸独立绘制（0-3 粒），药丸带有高光，保证 OpenCV 的轮廓检测算法能 100% 精准识别出对应的药丸数量。

## 拟定修改内容

### 1. 模拟器支持多药丸绘制与循环切换
在模拟器中，把 `slot_states` 从布尔值改为整数（0-3），并在药格内绘制对应数量的、带有高光的独立小圆圈。
- 按 `r` 键循环切换“早上”药格药丸数：`0 -> 1 -> 2 -> 3 -> 0`
- 按 `g` 键循环切换“中午”药格药丸数
- 按 `b` 键循环切换“晚上”药格药丸数

### 2. MedicationTracker 增加药量校验与警报
- 预设标准用量：`Morning = 1`, `Noon = 2`, `Evening = 1`。
- 在 `result.present` 时更新 `self.last_pill_count[key] = result.pill_count`。
- 当药格变空确认服药时，比较 `self.last_pill_count[key]` 与预设用量：
  - 如果一致，判定为正常确认；
  - 如果不一致（多拿或少拿），反馈状态置为 `"dosage_error"`（显示为橙色 `DOSAGE ERROR`），并打印 `[ALARM]` 级别事件，模拟触发语音警报。

---

### 组件修改细节

#### [修改] [smart_pillbox_opencv.py](file:///d:/interface/smart_pillbox_opencv.py)

我们将对主程序进行更新，重构 `MedicationTracker` 类和模拟器绘制相关的函数。

**主要修改部分预览：**

```python
# 1. 预设每种药一次要吃多少
self.expected_dosage = {
    "Morning": 1,  # 早上 1 粒
    "Noon": 2,     # 中午 2 粒
    "Evening": 1   # 晚上 1 粒
}

# 2. 状态变化逻辑（以 update 内的 present 为例）
if result.present:
    self.pending_since[key] = None
    self.confirmed[key] = False
    self.last_pill_count[key] = result.pill_count  # 记录变空前的药丸数
    
    # 实时校验药格内的药量是否正确
    if result.pill_count == self.expected_dosage[key]:
        feedback = SlotFeedback("ready", f"FULL / Pills: {result.pill_count}", (100, 255, 100))
    else:
        feedback = SlotFeedback("wrong_ready", f"WRONG DOSAGE ({result.pill_count}/{self.expected_dosage[key]})", (0, 102, 255))
else:
    # 变空后校验实际吃了几粒
    actual_taken = self.last_pill_count[key]
    dosage_ok = (actual_taken == self.expected_dosage[key])
    
    # 吞咽确认时...
    if dosage_ok:
        feedback = SlotFeedback("confirmed", "CONFIRMED: TAKEN", (80, 240, 120))
        # 记录正常服药事件...
    else:
        feedback = SlotFeedback("dosage_error", f"DOSAGE ERROR: TAKEN {actual_taken}", (0, 102, 255))
        events.append(self._format_event(key, "dosage_error", expected=self.expected_dosage[key], actual=actual_taken))
```

---

## 验证计划

### 模拟器交互验证

1. **测试剂量正确时的确认：**
   - 运行模拟器。早上药格（预设 1 粒）内有 1 粒药，显示为绿色 `FULL / Pills: 1`。
   - 按 `r` 拿走药丸，按 `s` 模拟吞咽。
   - 观察状态变为绿色的 `CONFIRMED: TAKEN`，终端打印正常服药打卡事件。

2. **测试剂量错误（少拿/多拿）时的警报：**
   - 早上药格状态复位。按 `r` 两次，使其显示为 `WRONG DOSAGE (2/1)`（放了 2 粒药，预设 1 粒）。
   - 按 `r` 两次拿走所有药丸（即一次性拿走了 2 粒药），按 `s` 模拟吞咽。
   - 观察状态变为橙色的 `DOSAGE ERROR: TAKEN 2`，且终端打印：`[ALARM] 早上服药剂量错误：应服 1 粒，实际取出 2 粒！已触发本地语音警报，提醒长者核对药量。`

3. **测试中午药格（预设 2 粒）：**
   - 按 `g` 将中午药格切换至 2 粒药，显示为绿色。
   - 拿走并模拟吞咽，确认为正常服药。如果切为 1 粒或 3 粒拿走并吞咽，应触发剂量错误警报。
