"""Small Chinese Tk desktop workflow: freeze -> label -> detect -> save -> export."""
from __future__ import annotations

import copy
import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import cv2
from PIL import Image, ImageTk

from .config import BenchError, load_config, save_config, validate_config
from .data import Batch, export_batch, now_iso
from .engine import BenchDetector, CameraSource, pixel_rect, read_image, transform_frame, make_demo_frame

KIND_LABELS = {"模拟物（流程测试）": "simulant", "真实药片": "real_pill", "软件测试夹具": "test_fixture"}
PHASE_LABELS = {"调参/探索": "tuning", "固定配置正式评估": "evaluation"}


class BenchApp:
    def __init__(self, root, config, config_path, output_root):
        self.root = root
        self.config = copy.deepcopy(config)
        self.config_path = Path(config_path)
        self.output_root = Path(output_root)
        self.camera = None
        self.raw = self.frame = None
        self.source = self.source_name = ""
        self.generated_fixture = False
        self.captured_at = None
        self.frozen = True
        self.batch = self.detector = None
        self.busy = False
        self.jobs = queue.Queue()
        self.drag = None
        self.photo = None
        self.fit = (1, 0, 0)
        self.counts = {}
        self.saved_captures = set()
        self.config_controls = []
        self.root.title("智能药盒 · 视觉台架测试（独立工具）")
        height = min(870, max(650, self.root.winfo_screenheight() - 100))
        self.root.geometry(f"1240x{height}")
        self.root.minsize(1100, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.status = tk.StringVar(value="先打开摄像头或图片，定格后拖动设置区域。尚未产生试验数据。")
        self.batch_text = tk.StringVar(value="尚未开始批次；配置可编辑")
        self.backend = tk.StringVar(value=config["detector"]["backend"])
        self.camera_index = tk.IntVar(value=config["camera_index"])
        self.mirror = tk.BooleanVar(value=config["mirror"])
        self.rotation = tk.StringVar(value=str(config["rotation"]))
        self.slot = tk.StringVar(value=config["slots"][0]["id"])
        self.kind = tk.StringVar(value=next(iter(KIND_LABELS)))
        self.phase = tk.StringVar(value=next(iter(PHASE_LABELS)))
        self.quality = tk.StringVar(value="可用（已人工查看）")
        self.fields = {k: tk.StringVar(value=v) for k, v in {
            "lighting": "室内均匀光", "background": "哑光深色背景", "angle": "固定俯拍",
            "overlap": "无", "occlusion": "无", "device": "请填写摄像头/电脑型号", "note": ""}.items()}
        self._build()
        self.root.after(80, self.tick)

    def _button(self, parent, text, command, *, config=False, row=None, column=None):
        button = ttk.Button(parent, text=text, command=lambda: self.guarded(command))
        if row is None:
            button.pack(side="left", padx=3, pady=3)
        else:
            button.grid(row=row, column=column, padx=3, pady=4, sticky="ew")
        if config:
            self.config_controls.append(button)
        return button

    def _build(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="视觉台架测试", font=("Microsoft YaHei", 19, "bold")).pack(anchor="w")
        ttk.Label(outer, text="3区域原型测试 · 保留原图与人工标注 · 不判断吞咽 · 不自动切换模拟器").pack(anchor="w", pady=(0, 8))
        settings = ttk.Frame(outer)
        settings.pack(fill="x")
        self._button(settings, "加载配置", self.load_settings, config=True)
        self._button(settings, "保存配置", self.save_settings, config=True)
        self._button(settings, "检测参数/权重", self.edit_parameters, config=True)
        ttk.Label(settings, text="后端").pack(side="left", padx=5)
        combo = ttk.Combobox(settings, textvariable=self.backend, values=("opencv", "yolo", "roboflow"), width=10, state="readonly")
        combo.pack(side="left")
        self.config_controls.append(combo)
        ttk.Label(settings, text="摄像头编号").pack(side="left", padx=5)
        spin = ttk.Spinbox(settings, from_=0, to=20, textvariable=self.camera_index, width=4)
        spin.pack(side="left")
        self.config_controls.append(spin)
        check = ttk.Checkbutton(settings, text="镜像", variable=self.mirror, command=lambda: self.guarded(self.refresh_transform))
        check.pack(side="left", padx=8)
        self.config_controls.append(check)
        ttk.Label(settings, text="顺时针旋转").pack(side="left")
        rotate = ttk.Combobox(settings, textvariable=self.rotation, values=("0", "90", "180", "270"), width=5, state="readonly")
        rotate.pack(side="left")
        rotate.bind("<<ComboboxSelected>>", lambda event: self.guarded(self.refresh_transform))
        self.config_controls.append(rotate)
        ttk.Label(outer, textvariable=self.status, wraplength=1190, relief="sunken", padding=7).pack(side="bottom", fill="x")
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True, pady=8)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.rowconfigure(0, weight=1)
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        right_panel = ttk.Frame(body)
        right_panel.grid(row=0, column=1, sticky="nsew")
        actions = ttk.Frame(right_panel)
        actions.pack(side="bottom", fill="x", pady=5)
        self.form_canvas = tk.Canvas(right_panel, width=365, highlightthickness=0)
        scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=self.form_canvas.yview)
        self.form_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.form_canvas.pack(side="left", fill="both", expand=True)
        right = ttk.Frame(self.form_canvas, padding=(0, 0, 6, 0))
        self.form_window = self.form_canvas.create_window((0, 0), window=right, anchor="nw")
        right.bind("<Configure>", lambda event: self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all")))
        self.form_canvas.bind("<Configure>", lambda event: self.form_canvas.itemconfigure(self.form_window, width=event.width))
        self.form_canvas.bind("<MouseWheel>", lambda event: self.form_canvas.yview_scroll(-int(event.delta/120), "units"))
        input_bar = ttk.Frame(left)
        input_bar.pack(fill="x")
        self._button(input_bar, "打开摄像头", self.open_camera)
        self._button(input_bar, "拍照/定格", self.freeze)
        self._button(input_bar, "继续预览", self.resume)
        self._button(input_bar, "打开图片", self.open_image)
        self._button(input_bar, "软件演练图", self.open_demo)
        self.canvas = tk.Canvas(left, background="#252b32", highlightthickness=0, width=760, height=280)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda event: self.render())
        self.canvas.bind("<ButtonPress-1>", self.drag_start)
        self.canvas.bind("<B1-Motion>", self.drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        roi_bar = ttk.Frame(left)
        roi_bar.pack(fill="x", pady=5)
        ttk.Label(roi_bar, text="拖动设置区域：").pack(side="left")
        self.slot_combo = ttk.Combobox(roi_bar, textvariable=self.slot, values=[s["id"] for s in self.config["slots"]], width=12, state="readonly")
        self.slot_combo.pack(side="left")
        self.config_controls.append(self.slot_combo)
        self._button(roi_bar, "改格子名称", self.rename_slot, config=True)
        ttk.Label(left, textvariable=self.batch_text, wraplength=740).pack(anchor="w", pady=4)
        self.result_text = tk.Text(left, height=6, wrap="word", font=("Microsoft YaHei", 10), state="disabled")
        self.result_text.pack(fill="x")
        ttk.Label(right, text="1. 开始批次（锁定参数）", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")
        batch_bar = ttk.Frame(right)
        batch_bar.pack(fill="x")
        self._button(batch_bar, "开始新批次", self.begin)
        self._button(batch_bar, "结束批次", self.end)
        self.annotation_box = ttk.LabelFrame(right, text="2. 人工数量（空白=未标注，0=空格）", padding=7)
        self.annotation_box.pack(fill="x", pady=7)
        self.rebuild_counts()
        form = ttk.Frame(right)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        fields = [("样本类型", self.kind, list(KIND_LABELS)), ("阶段", self.phase, list(PHASE_LABELS)),
                  ("画面质量", self.quality, ["可用（已人工查看）", "手部遮挡", "严重反光", "区域偏移", "明显失焦", "其他不可判断"])]
        for row, (label, var, choices) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Combobox(form, textvariable=var, values=choices, state="readonly", width=25).grid(row=row, column=1, sticky="ew", pady=3)
        for row, (key, label) in enumerate([("lighting", "光照"), ("background", "背景"), ("angle", "角度"),
                                           ("overlap", "重叠"), ("occlusion", "遮挡"), ("device", "设备型号"), ("note", "备注")], start=3):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(form, textvariable=self.fields[key], width=27).grid(row=row, column=1, sticky="ew", pady=3)
        self._button(actions, "3. 检测并保存样本", self.save_sample, row=0, column=0)
        self._button(actions, "4. 导出当前批次", self.export, row=1, column=0)
        self._button(actions, "导出已有批次", self.export_existing, row=2, column=0)
        ttk.Label(right, text="OpenCV初始配置：浅色药片+哑光深色托盘。\n浅色背景、接触/重叠需单独测试。\n有遮挡时请选择“不可判断”。\n每次新画面会清空人工数量。\n正式评估前冻结参数，独立重新摆放样本。", wraplength=345).pack(anchor="w")

    def guarded(self, action):
        if self.busy:
            messagebox.showinfo("正在处理", "请等待本次检测或导出完成", parent=self.root)
            return
        try:
            action()
        except Exception as exc:
            self.status.set(str(exc))
            messagebox.showerror("操作未完成", str(exc), parent=self.root)

    def sync_config(self):
        if self.batch is None:
            self.config["camera_index"] = self.camera_index.get()
            self.config["mirror"] = self.mirror.get()
            self.config["rotation"] = int(self.rotation.get())
            self.config["detector"]["backend"] = self.backend.get()
        validate_config(self.config)

    def set_controls(self, locked):
        for widget in self.config_controls:
            widget.configure(state="disabled" if locked else ("readonly" if isinstance(widget, ttk.Combobox) else "normal"))

    def rebuild_counts(self):
        for child in self.annotation_box.winfo_children():
            child.destroy()
        self.counts = {}
        for i, slot in enumerate(self.config["slots"]):
            var = tk.StringVar(value="")
            self.counts[slot["id"]] = var
            ttk.Label(self.annotation_box, text=f"{slot['name']} ({slot['id']})").grid(row=i, column=0, sticky="w")
            ttk.Entry(self.annotation_box, textvariable=var, width=8).grid(row=i, column=1, padx=12, pady=3)

    def clear_counts(self):
        for var in self.counts.values():
            var.set("")
        self.quality.set("可用（已人工查看）")
        self.show_results("")

    def show_results(self, text):
        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.result_text.configure(state="disabled")

    def close_camera(self):
        if self.camera is not None:
            self.camera.close()
            self.camera = None

    def open_camera(self):
        self.sync_config()
        self.close_camera()
        self.raw = self.frame = None
        self.frozen = True
        self.canvas.delete("all")
        self.clear_counts()
        self.camera = CameraSource(self.config["camera_index"])
        self.generated_fixture = False
        self.source, self.source_name = "camera", f"camera:{self.config['camera_index']}"
        self.frozen = False
        self.status.set("真实摄像头预览中；按“拍照/定格”后标注。检测后端不会自动更换。")

    def freeze(self):
        if self.frame is None:
            raise BenchError("请先打开摄像头或图片")
        self.frozen = True
        self.clear_counts()
        self.status.set("已定格；设置区域后开始批次，填写人工数量再检测保存。")

    def resume(self):
        if self.camera is None:
            raise BenchError("摄像头未打开，请重新打开摄像头")
        self.frozen = False
        self.clear_counts()
        self.status.set("恢复真实摄像头预览；请重新摆放，再定格拍摄")

    def open_image(self):
        path = filedialog.askopenfilename(title="选择本地原始图片", filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("所有文件", "*.*")])
        if not path:
            return
        raw = read_image(Path(path))
        self.sync_config()
        self.close_camera()
        self.raw, self.frame = raw, transform_frame(raw, self.config)
        self.generated_fixture = False
        self.source, self.source_name, self.captured_at = "image", Path(path).name, now_iso()
        self.frozen = True
        self.clear_counts()
        self.render()
        self.status.set(f"已载入图片 {Path(path).name}；原图保留，采集时间字段为本次导入时间。")

    def open_demo(self):
        self.sync_config()
        self.close_camera()
        # Generate in the configured ROI coordinate system; undo the input transform
        # to obtain raw pixels, then apply the normal pipeline exactly once.
        frame, known = make_demo_frame(self.config)
        raw = cv2.flip(frame, 1) if self.config["mirror"] else frame.copy()
        if self.config["rotation"]:
            inverse = {90: cv2.ROTATE_90_COUNTERCLOCKWISE, 180: cv2.ROTATE_180,
                       270: cv2.ROTATE_90_CLOCKWISE}[self.config["rotation"]]
            raw = cv2.rotate(raw, inverse)
        self.raw, self.frame = raw, transform_frame(raw, self.config)
        self.source, self.source_name, self.captured_at = "image", "SOFTWARE_TEST_FIXTURE", now_iso()
        self.generated_fixture, self.frozen = True, True
        self.clear_counts()
        self.kind.set("软件测试夹具")
        self.phase.set("调参/探索")
        self.fields["device"].set("软件生成圆片（非摄像头照片）")
        self.fields["lighting"].set("软件生成固定亮度")
        self.fields["background"].set("软件生成深灰背景")
        self.fields["angle"].set("软件生成平面图")
        self.fields["overlap"].set("无")
        self.fields["occlusion"].set("无")
        self.fields["note"].set("仅用于软件演练，不是真实药片试验")
        hint = " / ".join(f"{slot['name']}={known[slot['id']]}" for slot in self.config["slots"])
        self.show_results(f"软件演练图已生成：{hint}。\n请自己填写数量练习标注；没有自动用预测填标签。")
        self.render()
        self.status.set("这是软件测试夹具。开始批次后填数量、检测保存并导出；不能标为真实药片。")

    def refresh_transform(self):
        self.sync_config()
        if self.raw is not None:
            self.frame = transform_frame(self.raw, self.config)
            self.clear_counts()
            self.render()

    def render(self):
        if self.frame is None:
            return
        frame = self.frame.copy()
        for slot in self.config["slots"]:
            try:
                x1, y1, x2, y2 = pixel_rect(frame, slot)
            except BenchError:
                continue
            color = (0, 200, 255) if slot["id"] == self.slot.get() else (120, 230, 150)
            cv2.rectangle(frame, (x1, y1), (x2-1, y2-1), color, 2)
            cv2.putText(frame, slot["id"], (x1+3, y1+20), cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
        cw, ch = max(20, self.canvas.winfo_width()), max(20, self.canvas.winfo_height())
        h, w = frame.shape[:2]
        scale = min(cw/w, ch/h)
        dw, dh = max(1, int(w*scale)), max(1, int(h*scale))
        ox, oy = (cw-dw)/2, (ch-dh)/2
        self.fit = (dw/w, dh/h, ox, oy)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb).resize((dw, dh), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(image, master=self.root)
        self.canvas.delete("all")
        self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")

    def image_point(self, event):
        if self.frame is None:
            return None
        sx, sy, ox, oy = self.fit
        h, w = self.frame.shape[:2]
        x, y = (event.x-ox)/sx, (event.y-oy)/sy
        return max(0, min(w, x))/w, max(0, min(h, y))/h

    def drag_start(self, event):
        if self.batch is not None or self.busy or not self.frozen or self.frame is None:
            return
        self.drag = self.image_point(event)

    def drag_move(self, event):
        if self.drag is None:
            return
        self.canvas.delete("selection")
        sx, sy, ox, oy = self.fit
        h, w = self.frame.shape[:2]
        end = self.image_point(event)
        self.canvas.create_rectangle(self.drag[0]*w*sx+ox, self.drag[1]*h*sy+oy,
                                     end[0]*w*sx+ox, end[1]*h*sy+oy, outline="#ffcc55", width=3, tags="selection")

    def drag_end(self, event):
        if self.drag is None:
            return
        start, end = self.drag, self.image_point(event)
        self.drag = None
        new_rect = [min(start[0],end[0]), min(start[1],end[1]), max(start[0],end[0]), max(start[1],end[1])]
        next_config = copy.deepcopy(self.config)
        for slot in next_config["slots"]:
            if slot["id"] == self.slot.get():
                slot["rect"] = new_rect
        try:
            validate_config(next_config)
            for slot in next_config["slots"]:
                pixel_rect(self.frame, slot)
        except BenchError as exc:
            self.status.set(str(exc))
            self.render()
            return
        self.config = next_config
        self.render()
        self.status.set("区域已更新；请检查三个区域互不重叠，并保存配置。")

    def rename_slot(self):
        name = simpledialog.askstring("格子名称", "填写当前格子的显示名称", parent=self.root)
        if not name or not name.strip():
            return
        for slot in self.config["slots"]:
            if slot["id"] == self.slot.get():
                slot["name"] = name.strip()
        self.rebuild_counts()

    def load_settings(self):
        path = filedialog.askopenfilename(title="加载台架配置", filetypes=[("JSON", "*.json")])
        if not path:
            return
        config = load_config(Path(path))
        self.close_camera()
        self.frozen = True
        self.config, self.config_path = config, Path(path)
        self.backend.set(config["detector"]["backend"])
        self.camera_index.set(config["camera_index"])
        self.mirror.set(config["mirror"])
        self.rotation.set(str(config["rotation"]))
        self.slot.set(config["slots"][0]["id"])
        self.slot_combo.configure(values=[s["id"] for s in config["slots"]])
        self.rebuild_counts()
        self.refresh_transform()
        self.status.set(f"已加载 {Path(path).name}；请核对区域与当前镜像/旋转方向")

    def save_settings(self):
        self.sync_config()
        path = filedialog.asksaveasfilename(title="保存台架配置", initialfile="bench.local.json", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            save_config(Path(path), self.config)
            self.config_path = Path(path)
            self.status.set(f"配置已保存：{path}")

    def edit_parameters(self):
        self.sync_config()
        dialog = tk.Toplevel(self.root)
        dialog.title("检测参数（开始批次后锁定）")
        dialog.geometry("650x680")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="编辑 detector / opencv / quality。YOLO需设置本地权重路径。\nHSV范围针对所有格子；不根据早中晚限制药片颜色。", padding=8).pack(anchor="w")
        text = tk.Text(dialog, wrap="none", font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=8)
        params = {k: self.config[k] for k in ("detector", "opencv", "quality")}
        text.insert("1.0", json.dumps(params, ensure_ascii=False, indent=2))
        def apply():
            try:
                changed = json.loads(text.get("1.0", "end"))
                if set(changed) != {"detector", "opencv", "quality"}:
                    raise BenchError("只编辑 detector / opencv / quality 三组参数")
                candidate = copy.deepcopy(self.config)
                candidate.update(changed)
                validate_config(candidate)
                self.config = candidate
                self.backend.set(candidate["detector"]["backend"])
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror("参数未保存", str(exc), parent=dialog)
        ttk.Button(dialog, text="验证并应用", command=apply).pack(pady=8)

    def begin(self):
        if self.batch is not None:
            raise BenchError("请先结束当前批次；不同配置不能混进同一批次")
        self.sync_config()
        if self.camera is not None and self.camera.index != self.config["camera_index"]:
            raise BenchError("摄像头编号已改变，请重新打开摄像头再采集")
        if self.frame is None or not self.frozen:
            raise BenchError("请先打开画面并定格，确认区域后开始批次")
        for slot in self.config["slots"]:
            pixel_rect(self.frame, slot)
        if self.backend.get() == "roboflow" and not messagebox.askyesno("确认云端检测", "本批次点击检测时，画面将发送至Roboflow，并可能消耗配额。\n请勿拍摄病历、姓名、面部或其他个人信息。是否启用？", parent=self.root):
            return
        self.detector = BenchDetector(self.config)
        self.batch = Batch(self.output_root, self.config, self.detector.identity)
        self.set_controls(True)
        self.batch_text.set(f"批次：{self.batch.batch_id} · {self.backend.get()} · {self.detector.identity['model']}\n配置锁定：{self.batch.config_id[:12]} · 原图与记录保存在 runs/bench 下")
        self.status.set("批次已开始；人工数量可留空，但未标注样本不会计算准确率。")

    def end(self):
        if self.batch is None:
            return
        if messagebox.askyesno("结束批次", "结束前导出当前批次？", parent=self.root):
            self.export()
            # Export is asynchronous; keep batch locked until callback.
            self.end_after_export = True
            return
        self.finish_end()

    def finish_end(self):
        self.batch = self.detector = None
        self.set_controls(False)
        self.batch_text.set("批次已结束；可修改参数后创建新批次。原始记录保留在本地。")

    def worker(self, task, success):
        self.busy = True
        self.status.set("正在处理，请稍候；网络失败不会回退算法……")
        def run():
            try:
                result = task()
                self.jobs.put((True, success, result))
            except Exception as exc:
                self.jobs.put((False, success, str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def save_sample(self):
        if self.batch is None or self.detector is None:
            raise BenchError("请先开始批次")
        if self.frame is None or not self.frozen:
            raise BenchError("请先拍照/定格，不能标注仍在变化的预览")
        capture_key = (self.batch.batch_id, self.captured_at)
        if capture_key in self.saved_captures:
            raise BenchError("这一张定格画面已保存；请重新采集，避免重复记录")
        counts = {}
        for key, var in self.counts.items():
            text = var.get().strip()
            if text and (not text.isascii() or not text.isdigit()):
                raise BenchError("人工数量只能填非负整数；未知请留空")
            counts[key] = int(text) if text else None
        if all(v is None for v in counts.values()) and not messagebox.askyesno("尚未标注", "本次没有人工数量，只保存未标注样本，不计算准确率。继续？", parent=self.root):
            return
        if self.generated_fixture and self.kind.get() != "软件测试夹具":
            raise BenchError("软件演练图必须标为软件测试夹具，不能当作真实药片或实拍模拟物")
        meta = {k: var.get().strip() for k, var in self.fields.items()}
        if meta["device"] == "请填写摄像头/电脑型号":
            raise BenchError("请填写实际设备型号，不清楚可写“未知型号”")
        meta.update(sample_kind=KIND_LABELS[self.kind.get()], phase=PHASE_LABELS[self.phase.get()],
                    source=self.source, source_name=self.source_name)
        quality = self.quality.get()
        manual_invalid = "" if quality.startswith("可用") else quality
        raw, frame = self.raw.copy(), self.frame.copy()
        batch, detector, captured = self.batch, self.detector, self.captured_at
        def task():
            observations = detector.detect(frame, manual_invalid)
            return batch.record(raw, frame, counts, meta, observations, detector, captured)
        def success(rows):
            self.saved_captures.add(capture_key)
            lines = [f"{r['slot_name']}：人工={r['ground_truth'] if r['ground_truth'] is not None else '未标注'}；"
                     f"预测={r['raw_prediction'] if r['raw_prediction'] is not None else '无法判断'}；{r['status']} {r['reason']}" for r in rows]
            self.show_results("\n".join(lines) + f"\n样本ID：{rows[0]['sample_id']}")
            self.status.set("样本和原图已保存。请重新摆放后继续预览/打开下一张图片；不要重复保存同一画面充当独立样本。")
        self.worker(task, success)

    def export(self):
        if self.batch is None:
            raise BenchError("没有当前批次；可以使用“导出已有批次”")
        self.export_path(self.batch.path)

    def export_existing(self):
        path = filedialog.askdirectory(title="选择含 manifest.json 的批次文件夹", initialdir=self.output_root)
        if path:
            self.export_path(Path(path))

    def export_path(self, path):
        def success(result):
            output, report = result
            self.status.set(f"已导出 {output}：records.csv、metrics.csv/json、failures.csv/html")
            self.show_results(f"已导出 {len(report['groups'])} 组统计。\n真实药片/模拟物/夹具及调参/评估分开。\n没有人工标注时不生成准确率。\n结果目录：{output}")
            if getattr(self, "end_after_export", False):
                self.end_after_export = False
                self.finish_end()
        self.worker(lambda: export_batch(path), success)

    def tick(self):
        try:
            while True:
                ok, callback, result = self.jobs.get_nowait()
                self.busy = False
                if ok:
                    callback(result)
                else:
                    self.end_after_export = False
                    self.status.set(result)
                    messagebox.showerror("处理未完成", result, parent=self.root)
        except queue.Empty:
            pass
        if self.camera is not None and not self.frozen and not self.busy:
            try:
                self.raw = self.camera.read()
                self.captured_at = now_iso()
                self.frame = transform_frame(self.raw, self.config)
                self.render()
            except Exception as exc:
                self.close_camera()
                self.raw = self.frame = None
                self.frozen = True
                self.canvas.delete("all")
                self.clear_counts()
                self.status.set(str(exc))
        self.root.after(80, self.tick)

    def close(self):
        if self.busy:
            messagebox.showinfo("正在处理", "请等待当前保存/导出完成后关闭", parent=self.root)
            return
        self.close_camera()
        self.root.destroy()


def launch(config, config_path, output_root):
    # Avoid Windows bitmap scaling on high-DPI displays; do not affect other apps.
    import os
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    BenchApp(root, config, config_path, output_root)
    root.mainloop()
