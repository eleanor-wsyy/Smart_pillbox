# C 任务验收记录

测试环境：本地 Vite :5173 + FastAPI :8000；无预置本地数据的浏览器上下文。截图为运行中的界面，不包含人为合成记录。

1. 数据层：`/api/status` 与 `/api/events` 并发轮询；空状态无病例/记录；调用模拟数量后设备事件进入历史；阻断 `/api/**` 时显示连接错误，不保留上次在线状态。截图 `01-dashboard.png`、`07-history.png`、`09-offline.png`。
2. 家庭圈：添加主/临时成员 → 发起交接（采集当时的计划及三格快照）→ 选择接手人确认 → 首页出现临时照看人及时间戳记录。截图 `02-family-handover.png`、`03-dashboard-handover.png`。
3. 病历录入：上传照片 → Tesseract.js 真实 OCR 转写原文（若网络/引擎故障，允许明确标识的人工录入）→ 手工填写并确认计划 → `/api/medplan` 同步数量。截图 `05-records-confirmed.png`。另用浏览器 Canvas 生成真实含 “Aspirin 1 tablet” 的图片，上传后运行 chi_sim+eng OCR 得到相同原文，并生成待人工核对的首行候选草稿；截图 `10-ocr-result.png`。真实中文病历识别质量仍需用获授权样本在目标演示环境单独验证。
4. 装药复核：选择药格/照片/批次并人工勾选；数量不符记录警告，不能完成；不同步或过期批次阻断。截图 `06-review-mismatch.png`。
5. 有效期：真实录入两个测试批次（正常、过期），过期高亮，提醒页依据库存显示提示；截图 `04-inventory.png`、`08-alerts.png`。

检查命令：`pnpm build`（前端构建），`pnpm exec tsc --noEmit --jsx react-jsx --module esnext --moduleResolution bundler --target es2022 --lib dom,es2022 --allowSyntheticDefaultImports --skipLibCheck src/app/App.tsx src/app/store.ts`（类型检查）。API 测试：`/api/status` 200、`/api/events` 200、`/api/medplan` 合法请求 200/超范围 422。

安全设计选择：保质期临期也暂停放行，要求更换非临期批次；设备失联不允许按旧状态复核；一格多药不冒险自动判定品种；无法证明吞咽，始终不标“已服用”。
补充端到端测试：过期批次即使药名及数量匹配也阻断；替换为有效批次后，早/中/晚三格逐格复核通过，完成按钮可用，记录页能检索到完成事件。使用全新浏览器上下文执行，没有复用截图测试的本地数据。
