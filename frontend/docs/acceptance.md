# C 任务验收记录（初版留档）

以下为初版逐格复核流程的历史验收，不代表后续简化后的装药记录页面。测试环境：本地 Vite :5173 + FastAPI :8000；无预置本地数据的浏览器上下文。

1. 数据层：`/api/status` 与 `/api/events` 并发轮询；空状态无病例/记录；调用模拟数量后设备事件进入历史；阻断 `/api/**` 时显示连接错误，不保留上次在线状态。截图 `01-dashboard.png`、`07-history.png`、`09-offline.png`。
2. 家庭圈：添加主/临时成员 → 发起交接（采集当时的计划及三格快照）→ 选择接手人确认 → 首页出现临时照看人及时间戳记录。截图 `02-family-handover.png`、`03-dashboard-handover.png`。
3. 病历录入：上传照片 → Tesseract.js 真实 OCR 转写原文（若网络/引擎故障，允许明确标识的人工录入）→ 手工填写并确认计划 → `/api/medplan` 同步数量。截图 `05-records-confirmed.png`。另用浏览器 Canvas 生成真实含 “Aspirin 1 tablet” 的图片，上传后运行 chi_sim+eng OCR 得到相同原文，并生成待人工核对的首行候选草稿；截图 `10-ocr-result.png`。真实中文病历识别质量仍需用获授权样本在目标演示环境单独验证。
4. 装药复核：选择药格/照片/批次并人工勾选；数量不符记录警告，不能完成；不同步或过期批次阻断。截图 `06-review-mismatch.png`。
5. 有效期：真实录入两个测试批次（正常、过期），过期高亮，提醒页依据库存显示提示；截图 `04-inventory.png`、`08-alerts.png`。

检查命令：`pnpm build`（前端构建），`pnpm exec tsc --noEmit --jsx react-jsx --module esnext --moduleResolution bundler --target es2022 --lib dom,es2022 --allowSyntheticDefaultImports --skipLibCheck src/app/App.tsx src/app/store.ts`（类型检查）。API 测试：`/api/status` 200、`/api/events` 200、`/api/medplan` 合法请求 200/超范围 422。

安全设计选择：保质期临期也暂停放行，要求更换非临期批次；设备失联不允许按旧状态复核；一格多药不冒险自动判定品种；无法证明吞咽，始终不标“已服用”。
补充端到端测试：过期批次即使药名及数量匹配也阻断；替换为有效批次后，早/中/晚三格逐格复核通过，完成按钮可用，记录页能检索到完成事件。使用全新浏览器上下文执行，没有复用截图测试的本地数据。

## 简化版装药记录（2026-10-10）

- 页面路径：首页 → 装药记录。选择本次已装好的早/中/晚药格，可只选早上；选择一张照片，核对自动显示的记录人、药格、计划名称和粒数，再保存。无需手填批次、身份核对勾选或三格全部完成。
- 自动记录：保存时间、当前照看人/主照顾人、所选药格及计划与设备粒数、压缩后的照片。仅当前浏览器 localStorage 保存最近 8 条，可回看或删除；旧版逐格记录独立展示且只有文件名。
- 阻断条件：未选药格或照片、无照看人、设备离线、所选药格无计划、设备计划不同步、检测粒数不符/识别不稳定、匹配的未处理过期库存。旧版的三格全部复核门槛已移除。
- 安全边界：不识别照片中的药物、批次及真实拍摄人；数量吻合不等于药品正确或已吞服。历史截图 06 仍为初版，不作为新版视觉验收。
- 新版检查：TypeScript 无报错、Vite build 成功；浏览器页面可选择单格或多格，缺计划药格明确提示且保存不可用；未上传照片的保存不可用。照片上传后的最终保存流程应在获授权的真实演示浏览器中再次验证。

## Windows 首次安装回归（2026-10-10）

- 在 Windows x64 上将当前源代码导出到两个全新隔离目录（无 `node_modules`、`dist`），分别执行 `npm ci && npm run build` 和 `pnpm install --frozen-lockfile && pnpm build`，均成功；没有手工安装缺失依赖。Node.js 24.15.0，npm 11.12.1，pnpm 11.25.0。
- 检查锁文件包含 tesseract.js、TypeScript、Windows x64 的 Tailwind/Esbuild 原生包；应用 TypeScript 指定文件检查无报错。
- 从隔离副本运行 Vite（5175）与 FastAPI（8000），网页 200、`/api/status` 200、Vite `/api/status` 代理 200；前端源码包含家庭圈入口。
- 这是**当前 Windows 主机的全新副本**，不是另一台物理电脑；另一台机器上的代理、Node/Python 版本、杀毒软件和网络仍需当地执行 README 命令复核。后端在此主机使用已有 Python 3.9 依赖做启动烟测，未在新机器从零安装 Python 依赖；浏览器 OCR 语言包也未在新机器实测。
