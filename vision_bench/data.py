"""Local immutable batches, per-sample evidence and explicit evaluation denominators."""
from __future__ import annotations

import copy
import csv
import html
import json
import os
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import cv2

from .config import BenchError, digest, validate_config
from .engine import _sha_file, write_image

KINDS = ("real_pill", "simulant", "test_fixture")
PHASES = ("tuning", "evaluation")
CSV_COLUMNS = [
    "batch_id", "sample_id", "captured_at", "saved_at", "source", "source_name", "device",
    "phase", "sample_kind", "lighting", "background", "angle", "overlap", "occlusion", "note",
    "config_id", "backend", "model", "confidence_kind", "slot_id", "slot_name", "ground_truth",
    "raw_prediction", "smoothed_prediction", "event", "status", "reason", "confidence",
    "quality", "frame_width", "frame_height", "raw_image", "input_image", "overlay_image",
    "raw_sha256", "input_sha256", "cloud_info",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def validate_metadata(meta):
    if meta.get("sample_kind") not in KINDS or meta.get("phase") not in PHASES:
        raise BenchError("请明确样本类型及调参/正式评估阶段")
    if meta.get("source") not in ("camera", "image"):
        raise BenchError("台架测试只接受摄像头或图片；不接受模拟器输出")
    for field in ("lighting", "background", "angle", "overlap", "occlusion", "device"):
        if not isinstance(meta.get(field), str) or not meta[field].strip():
            raise BenchError(f"请填写 {field}，不确定可写 unknown/未记录")


class Batch:
    def __init__(self, root: Path, config: dict, identity: dict):
        validate_config(config)
        self.config, self.identity = copy.deepcopy(config), copy.deepcopy(identity)
        self.config_id = digest({"config": self.config, "detector": self.identity})
        self.batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self.path = Path(root).resolve() / self.batch_id
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / "samples").mkdir()
        self.manifest = {
            "schema_version": 1, "batch_id": self.batch_id, "created_at": now_iso(),
            "config_id": self.config_id, "config": self.config, "detector": self.identity,
            "scope": "bench-test; no medication events; not a 21-slot integration test",
            "unit": "one manually labelled slot in one captured image",
        }
        save_json(self.path / "manifest.json", self.manifest)

    def record(self, raw, frame, counts: dict, metadata: dict, observations: dict, detector,
               captured_at=None):
        validate_metadata(metadata)
        if digest({"config": detector.config, "detector": detector.identity}) != self.config_id:
            raise BenchError("模型或配置已变更，请结束当前批次并创建新批次")
        if frame is None or raw is None:
            raise BenchError("没有有效画面，不创建药量为0的记录")
        slot_ids = {s["id"] for s in self.config["slots"]}
        if set(counts) != slot_ids or set(observations) != slot_ids:
            raise BenchError("标注/预测必须与当前格子ID完全对应")
        for value in counts.values():
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise BenchError("人工数量应为非负整数；未标注请留空")
        sample_id = uuid.uuid4().hex
        pending = Path(tempfile.mkdtemp(prefix=".pending_", dir=self.path / "samples"))
        # Incomplete saves stay .pending and are not included in evaluation.
        write_image(pending / "raw.png", raw)
        write_image(pending / "input.png", frame)
        overlay = frame.copy()
        for slot in self.config["slots"]:
            from .engine import pixel_rect
            try:
                x1, y1, x2, y2 = pixel_rect(frame, slot)
            except BenchError:
                continue
            obs = observations[slot["id"]]
            color = (40, 190, 40) if obs.status == "ok" else (20, 150, 240)
            cv2.rectangle(overlay, (x1, y1), (x2-1, y2-1), color, 2)
            if obs.result is not None:
                cv2.drawContours(overlay, obs.result.contours, -1, (0, 220, 0), 2)
                cv2.putText(overlay, f"{slot['id']}: {obs.result.pill_count}", (x1+3, y1+20),
                            cv2.FONT_HERSHEY_SIMPLEX, .5, color, 1)
        write_image(pending / "overlay.png", overlay)
        raw_sha, input_sha = _sha_file(pending / "raw.png"), _sha_file(pending / "input.png")
        stem = f"samples/{sample_id}"
        rows = []
        for slot in self.config["slots"]:
            obs = observations[slot["id"]]
            result = obs.result
            if obs.status == "ok" and (result is None or not isinstance(result.pill_count, int) or result.pill_count < 0):
                raise BenchError("有效预测缺少非负整数计数")
            row = {k: copy.deepcopy(metadata.get(k, "")) for k in CSV_COLUMNS}
            row.update(batch_id=self.batch_id, sample_id=sample_id, captured_at=captured_at or now_iso(),
                       saved_at=now_iso(), config_id=self.config_id, backend=self.identity["backend"],
                       model=self.identity["model"], confidence_kind=self.identity["confidence_kind"],
                       slot_id=slot["id"], slot_name=slot["name"], ground_truth=counts[slot["id"]],
                       raw_prediction=result.pill_count if obs.status == "ok" else None,
                       smoothed_prediction=None, event=None, status=obs.status, reason=obs.reason,
                       confidence=result.confidence if result is not None else None,
                       quality=obs.quality or {}, frame_width=frame.shape[1], frame_height=frame.shape[0],
                       raw_image=f"{stem}/raw.png", input_image=f"{stem}/input.png",
                       overlay_image=f"{stem}/overlay.png", raw_sha256=raw_sha, input_sha256=input_sha,
                       cloud_info=getattr(detector, "last_cloud_info", {}))
            rows.append(row)
        save_json(pending / "sample.json", {"schema_version": 1, "rows": rows})
        os.replace(pending, self.path / "samples" / sample_id)
        return rows


def load_rows(batch_path: Path, verify_images=True):
    batch_path = Path(batch_path).resolve()
    manifest = json.loads((batch_path / "manifest.json").read_text(encoding="utf-8"))
    expected_id = digest({"config": manifest["config"], "detector": manifest["detector"]})
    if manifest["config_id"] != expected_id:
        raise BenchError("批次配置或模型信息被修改，不能按原批次评估")
    rows = []
    seen = set()
    for path in sorted((batch_path / "samples").glob("*/sample.json")):
        if path.parent.name.startswith("."):
            continue
        sample_rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
        if len(sample_rows) != len(manifest["config"]["slots"]):
            raise BenchError(f"样本记录不完整：{path.parent.name}")
        for row in sample_rows:
            key = (row["sample_id"], row["slot_id"])
            if key in seen or row["config_id"] != expected_id or row["batch_id"] != manifest["batch_id"]:
                raise BenchError("记录重复或批次标识不一致")
            seen.add(key)
            validate_metadata(row)
            if (row["slot_id"] not in {s["id"] for s in manifest["config"]["slots"]}
                    or row["sample_id"] != path.parent.name
                    or row["backend"] != manifest["detector"]["backend"]
                    or row["model"] != manifest["detector"]["model"]):
                raise BenchError("记录中的格子、样本或检测后端与批次不一致")
            for label in ("ground_truth", "raw_prediction"):
                value = row[label]
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                    raise BenchError("记录中的数量无效")
            if row["status"] not in ("ok", "uncertain", "error"):
                raise BenchError("记录中的检测状态无效")
            if row["status"] == "ok" and row["raw_prediction"] is None:
                raise BenchError("有效预测缺少数量")
            if row["status"] != "ok" and row["raw_prediction"] is not None:
                raise BenchError("无法判断或错误不应记录有效数量")
            for field, sha in (("raw_image", "raw_sha256"), ("input_image", "input_sha256")):
                image_path = (batch_path / row[field]).resolve()
                if not image_path.is_relative_to(batch_path / "samples"):
                    raise BenchError("图片路径超出批次目录")
                if verify_images and _sha_file(image_path) != row[sha]:
                    raise BenchError(f"原始图片已改变：{row['sample_id']}")
            rows.append(row)
    return manifest, rows


def metrics(rows):
    labelled = [r for r in rows if r["ground_truth"] is not None]
    valid = [r for r in labelled if r["status"] == "ok" and r["raw_prediction"] is not None]
    matching = sum(r["raw_prediction"] == r["ground_truth"] for r in valid)
    return {
        "slot_observations": len(rows), "images": len({r["sample_id"] for r in rows}),
        "labelled": len(labelled), "unlabelled": len(rows) - len(labelled),
        "valid_predictions_labelled": len(valid), "failed_labelled": len(labelled) - len(valid),
        "failed_all": sum(r["status"] != "ok" for r in rows), "exact_matches": matching,
        "coverage": len(valid) / len(labelled) if labelled else None,
        "exact_rate_all_labelled": matching / len(labelled) if labelled else None,
        "exact_rate_valid_only": matching / len(valid) if valid else None,
        "mae_valid_only": sum(abs(r["raw_prediction"] - r["ground_truth"]) for r in valid) / len(valid) if valid else None,
    }


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    # User-entered descriptions must not execute as spreadsheet formulas.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        value = "'" + value
    return value


def write_csv(path, columns, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: csv_value(row.get(k)) for k in columns})


def export_batch(batch_path: Path):
    manifest, rows = load_rows(batch_path)
    output = Path(batch_path) / "exports"
    output.mkdir(exist_ok=True)
    write_csv(output / "records.csv", CSV_COLUMNS, rows)
    base_fields = ["config_id", "backend", "model", "source", "sample_kind", "phase"]
    groups = defaultdict(list)
    for row in rows:
        # Never mix real pills, simulants, fixtures, tuning, evaluation or source modes.
        base = tuple(row[k] for k in base_fields)
        groups[(base, "all", "all")].append(row)
        for field in ("lighting", "background", "angle", "overlap", "occlusion", "ground_truth", "slot_id"):
            groups[(base, field, str(row[field]))].append(row)
    summaries = []
    for (base, dimension, value), members in sorted(groups.items()):
        summary = dict(zip(base_fields, base))
        summary.update(dimension=dimension, value=value, **metrics(members))
        summaries.append(summary)
    columns = base_fields + ["dimension", "value"] + list(metrics([]))
    write_csv(output / "metrics.csv", columns, summaries)
    report = {
        "batch_id": manifest["batch_id"], "created_at": now_iso(), "groups": summaries,
        "overall_mixed_accuracy": None,
        "notes": ["统计单位为一张图片中的一个人工标注药格，不是独立患者或服药次数。",
                  "同一画面连续重复拍摄不能当成独立场景样本。",
                  "exact_rate_all_labelled=完全匹配数/全部已标注格子；失败计入分母。",
                  "coverage=有效预测数/已标注格子；MAE和valid_only准确率仅在有效预测上计算。",
                  "未标注数据不计算准确率；没有数据返回null；所有阶段及样本类型分开统计。",
                  "OpenCV confidence是掩膜工程分数；模型confidence也不等于实测准确率。"],
    }
    save_json(output / "metrics.json", report)
    failures = [r for r in rows if r["status"] != "ok" or
                (r["ground_truth"] is not None and r["raw_prediction"] != r["ground_truth"])]
    write_csv(output / "failures.csv", CSV_COLUMNS, failures)
    cards = []
    for r in failures:
        img = "../" + quote(r["overlay_image"], safe="/")
        text = {k: html.escape(str(r[k])) for k in ("sample_id", "slot_name", "ground_truth", "raw_prediction", "reason", "status")}
        cards.append(f'<article><h2>{text["slot_name"]} · {text["status"]}</h2>'
                     f'<p>样本 {text["sample_id"]}<br>人工数量：{text["ground_truth"]}；预测：{text["raw_prediction"]}'
                     f'<br>{text["reason"]}</p><a href="{img}"><img src="{img}" alt="本地失败样本"></a></article>')
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>台架测试失败样本</title>'
            '<style>body{font:16px/1.6 "Microsoft YaHei",sans-serif;margin:32px;background:#f5f6f8}'
            'main{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:20px}'
            'article{background:white;padding:18px;border:1px solid #ddd}img{max-width:100%}h2{font-size:18px}</style>'
            '<h1>台架测试失败样本</h1><p>仅本地展示；数量不符和无法判断均保留。本页不证明服药。</p><main>'
            + ("".join(cards) or '<p>当前没有已记录的失败样本；不代表测试已经充分。</p>') + '</main></html>')
    (output / "failures.html").write_text(page, encoding="utf-8")
    return output, report


def write_template(path: Path, config: dict):
    rows = [{"slot_id": s["id"], "slot_name": s["name"]} for s in config["slots"]]
    write_csv(path, CSV_COLUMNS, rows)
