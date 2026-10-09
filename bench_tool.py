"""Chinese desktop workflow and reproducible offline vision bench captures."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from vision_bench.config import BenchError, default_config, load_config, save_config
from vision_bench.data import Batch, KINDS, PHASES, export_batch, now_iso, write_template
from vision_bench.engine import BenchDetector, read_image, transform_frame

BASE = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE / "configs" / "bench.example.json"
DEFAULT_RUNS = BASE / "runs" / "bench"


def parser():
    main = argparse.ArgumentParser(description="智能药盒视觉台架测试：本地采集、人工标注与评估，不生成服药事件")
    commands = main.add_subparsers(dest="command")
    gui = commands.add_parser("gui", help="打开中文桌面工具（默认）")
    gui.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    gui.add_argument("--output", type=Path, default=DEFAULT_RUNS)
    init = commands.add_parser("init-config", help="生成初始配置")
    init.add_argument("--output", type=Path, required=True)
    record = commands.add_parser("record", help="记录并检测一张本地原始图片，无需摄像头")
    record.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    record.add_argument("--image", type=Path, required=True)
    record.add_argument("--counts", help="按配置格子顺序，如 2,1,3；未知留空，如 2,,3")
    record.add_argument("--kind", choices=KINDS, required=True)
    record.add_argument("--phase", choices=PHASES, default="tuning")
    for key in ("lighting", "background", "angle", "overlap", "occlusion", "device"):
        record.add_argument("--" + key, default="未记录")
    record.add_argument("--note", default="")
    record.add_argument("--invalid", default="", help="画面不可用的原因；保留样本但不输出零数量")
    record.add_argument("--output", type=Path, default=DEFAULT_RUNS)
    export = commands.add_parser("export", help="从原图校验通过的已保存批次重新导出")
    export.add_argument("--batch", type=Path, required=True)
    template = commands.add_parser("template", help="生成空白CSV记录模板")
    template.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    template.add_argument("--output", type=Path, required=True)
    return main


def parse_counts(text, slots):
    values = text.split(",") if text is not None else [""] * len(slots)
    if len(values) != len(slots):
        raise BenchError(f"数量列数必须与配置中的 {len(slots)} 个格子一致")
    counts = {}
    for slot, value in zip(slots, values):
        value = value.strip()
        if value and (not value.isascii() or not value.isdigit()):
            raise BenchError("人工数量必须是非负整数；未知留空")
        counts[slot["id"]] = int(value) if value else None
    return counts


def run(args):
    if args.command == "init-config":
        if args.output.exists():
            raise BenchError("配置已存在，拒绝覆盖；请选择新文件名")
        save_config(args.output, default_config())
        print(f"已生成配置：{args.output.resolve()}")
    elif args.command == "export":
        output, report = export_batch(args.batch)
        print(json.dumps({"output": str(output.resolve()), "groups": report["groups"]}, ensure_ascii=False, indent=2))
    elif args.command == "template":
        if args.output.exists():
            raise BenchError("模板已存在，拒绝覆盖；请选择新文件名")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_template(args.output, load_config(args.config))
        print(f"已生成空白模板：{args.output.resolve()}")
    elif args.command == "record":
        config = load_config(args.config)
        counts = parse_counts(args.counts, config["slots"])
        raw = read_image(args.image)
        captured_at = now_iso()
        frame = transform_frame(raw, config)
        detector = BenchDetector(config)
        batch = Batch(args.output, config, detector.identity)
        metadata = {k: getattr(args, k) for k in ("phase", "lighting", "background", "angle", "overlap", "occlusion", "device", "note")}
        metadata.update(sample_kind=args.kind, source="image", source_name=args.image.name)
        rows = batch.record(raw, frame, counts, metadata, detector.detect(frame, args.invalid), detector, captured_at)
        output, report = export_batch(batch.path)
        print(json.dumps({"batch": str(batch.path), "output": str(output), "rows": rows,
                          "all_groups": [g for g in report["groups"] if g["dimension"] == "all"]}, ensure_ascii=False, indent=2))
        return 2 if any(r["status"] != "ok" for r in rows) else 0
    else:
        from vision_bench.gui import launch
        config_path = getattr(args, "config", DEFAULT_CONFIG)
        launch(load_config(config_path), config_path, getattr(args, "output", DEFAULT_RUNS))
    return 0


def main():
    args = parser().parse_args()
    try:
        return run(args)
    except (BenchError, OSError, json.JSONDecodeError) as exc:
        print(f"操作未完成：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
