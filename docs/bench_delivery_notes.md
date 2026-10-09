# 本轮代码交付记录

## 范围

新增独立视觉台架工具；基于原仓库提交 `74cdadd103662135b6b8267db1cb436caa418b7e`。

原 `smart_pillbox_opencv.py`、`api_server.py` 和React前端保持不变。原演示入口自动切换模拟器/原API模拟输入的行为仍存在；严格输入与评估规则只适用于新增 `bench_tool.py`。

## 新增/修改

- `bench_tool.py`：GUI及配置、图片记录、导出、空模板命令。
- `vision_bench/config.py`：可验证/保存的区域和检测参数。
- `vision_bench/engine.py`：严格摄像头输入，OpenCV轮廓基线、本地YOLO适配、Roboflow HTTP适配，复用原接口和掩膜操作。
- `vision_bench/data.py`：冻结批次、原图与输入图、逐格标注/预测、校验及分组统计、失败图册。
- `vision_bench/gui.py`：中文桌面工作流，参数锁定、重复定格防护、异步推理/导出、无药品软件演练图。软件演练图禁止标为真实药片，人工标签仍需自行填写。
- `tests/test_vision_bench.py`、`tests/test_gui_smoke.py`：软件与隐藏GUI测试。
- `configs/bench.example.json`、`requirements-bench.txt`、`.env.bench.example`：配置/最小依赖/密钥环境变量示例。
- `setup_bench.cmd`：Windows首次安装，创建虚拟环境并安装最小依赖。
- `start_bench.cmd`、`start_bench.ps1`：Windows启动入口。
- `README.md`、`.gitignore`：增加操作入口及本地数据/密钥排除规则。
- `docs/vision_bench_guide.md`：中文操作与首轮实验清单。
- `docs/bench_record_template.csv`：空白模板，没有人工标签或预测数据。
- `docs/bench_ui_fixture.png`：软件生成圆片的GUI验收截图，不是真实药片照片。

## 验证

- `python -m unittest discover -s tests -v`：49项通过，包含7项隐藏GUI工作流测试；均不访问真实摄像头。
- `python -m compileall -q bench_tool.py vision_bench tests`：通过。
- `git diff --check`：通过。
- 命令行端到端：软件夹具2/1/3计数与导出；手遮挡保留样本且退出2；部分未标注保留空值；图片缺失不产生假记录；重导出与CSV BOM验证通过。
- GUI截图检查：右侧表单可滚动，检测/导出固定，结果和状态可见；截图样本标为test_fixture。
- 另外创建不继承系统包的干净虚拟环境，从 `requirements-bench.txt` 安装依赖：Python 3.13、OpenCV 4.14.0、NumPy 2.5.3、Pillow 12.3.0；49项测试及 `pip check` 通过，user site=False。队友按说明或首次安装脚本新建独立环境；虚拟环境不入库。

## 未验证

真实摄像头/真实药片、专用YOLO权重的实际推理、Roboflow真实密钥及线上响应、最终21格药盒整机。YOLO及云端自动测试使用模拟对象/响应，没有真实性能结论。

现阶段没有真实药片准确率，没有服药依从性数据，没有硬件联调结果。下一步是按操作说明采集独立真实样本，正式评估前固定模型与配置。

发布方式：独立 `vision-bench` 分支，不直接改动 `main`；提交号以GitHub分支记录为准。Windows干净环境已验证，macOS/Linux只提供安装说明，尚未做真机验证。
