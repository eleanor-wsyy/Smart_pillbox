# Smart Pillbox V4 Flowchart

## No Swallow Version

```mermaid
flowchart LR
    A["步骤 1: 视频输入<br/>单摄像头实时流"] --> B["步骤 2: 视觉检测<br/>Roboflow / YOLO"]
    B --> C["输出<br/>bbox / class / confidence / pill_count"]
    C --> D["步骤 3: 空间映射<br/>OpenCV ROI -> Morning / Noon / Evening"]
    D --> E["步骤 4: 事件生成<br/>previous_pill_count > current_pill_count"]
    E --> F{"生成 TAKE_MED_EVENT?"}
    F -->|No| G{"当前时段是否超时?"}
    G -->|No| H["MONITORING<br/>继续检测"]
    G -->|Yes| I["MISSED_RISK<br/>提醒老人取药"]
    F -->|Yes| J["步骤 5: 状态决策"]
    J --> K{"是否当前时段药格?"}
    K -->|No| L["LOCKED_WRONG_SLOT<br/>错误孔位取药"]
    K -->|Yes| M{"取出数量是否匹配处方?"}
    M -->|No| N["WARNING_DOSAGE<br/>剂量异常"]
    M -->|Yes| O["NORMAL_SUCCESS<br/>正确取药已确认"]
    B --> P{"置信度是否过低?"}
    P -->|Yes| Q["UNCERTAIN<br/>暂停判定并提示调整画面"]
    L --> R["RECOVERY<br/>放回药丸后恢复监控"]
    N --> S["输出反馈<br/>界面状态 / 指示灯 / 系统日志 / 家属通知"]
    I --> S
    O --> S
    Q --> S
    R --> S
```

