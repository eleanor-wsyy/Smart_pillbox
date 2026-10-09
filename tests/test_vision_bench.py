"""Software tests use generated fixtures only, never real-drug experiment data."""
import copy
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import cv2
import numpy as np

from bench_tool import parse_counts
from vision_bench.config import BenchError, default_config, load_config, save_config, validate_config
from vision_bench.data import Batch, csv_value, export_batch, load_rows, metrics, write_template
from vision_bench.engine import BenchDetector, CameraSource, pixel_rect, read_image, transform_frame, write_image


def fixture(counts=(2, 1, 3)):
    """Generated white discs on gray background; not photographed pills."""
    frame = np.full((400, 800, 3), 35, np.uint8)
    config = default_config()
    for slot, count in zip(config["slots"], counts):
        x1, y1, x2, y2 = pixel_rect(frame, slot)
        for i in range(count):
            cx = (x1+x2)//2 + (i-(count-1)/2)*47
            cv2.circle(frame, (int(cx), (y1+y2)//2), 13, (230, 230, 230), -1)
    return frame


def metadata(**extra):
    data = {"source": "image", "source_name": "generated_test_fixture.png", "device": "software fixture",
            "sample_kind": "test_fixture", "phase": "tuning", "lighting": "generated",
            "background": "generated dark gray", "angle": "generated", "overlap": "none",
            "occlusion": "none", "note": "Software test only; not real-drug evidence"}
    data.update(extra)
    return data


class ConfigTests(unittest.TestCase):
    def test_config_round_trip_unicode_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "中文配置.json"
            save_config(path, default_config())
            self.assertEqual(load_config(path), default_config())

    def test_out_of_range_roi_rejected(self):
        c = default_config(); c["slots"][0]["rect"][0] = -0.1
        with self.assertRaises(BenchError): validate_config(c)

    def test_overlapping_rois_rejected(self):
        c = default_config(); c["slots"][1]["rect"] = c["slots"][0]["rect"]
        with self.assertRaises(BenchError): validate_config(c)

    def test_duplicate_slot_ids_rejected(self):
        c = default_config(); c["slots"][1]["id"] = "Morning"
        with self.assertRaises(BenchError): validate_config(c)

    def test_nan_threshold_rejected(self):
        c = default_config(); c["opencv"]["min_area_ratio"] = float("nan")
        with self.assertRaises(BenchError): validate_config(c)

    def test_hsv_bounds_rejected(self):
        c = default_config(); c["opencv"]["hsv_ranges"] = [[[180, 0, 0], [179, 255, 255]]]
        with self.assertRaises(BenchError): validate_config(c)

    def test_class_whitelist_must_be_list(self):
        c = default_config(); c["detector"]["allowed_classes"] = "pill"
        with self.assertRaises(BenchError): validate_config(c)

    def test_counts_blank_is_not_zero(self):
        self.assertEqual(parse_counts("2,,0", default_config()["slots"]), {"Morning": 2, "Noon": None, "Evening": 0})

    def test_invalid_counts_rejected(self):
        for text in ("2,1", "-1,1,3", "1.5,1,3", "true,1,3"):
            with self.assertRaises(BenchError): parse_counts(text, default_config()["slots"])


class InputAndDetectorTests(unittest.TestCase):
    def test_unicode_image_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "测试图片.png"
            write_image(path, fixture())
            np.testing.assert_array_equal(read_image(path), fixture())

    def test_invalid_image_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "not.png"; p.write_text("bad")
            with self.assertRaises(BenchError): read_image(p)

    def test_camera_open_failure_is_explicit(self):
        cap = Mock(); cap.isOpened.return_value = False
        with self.assertRaisesRegex(BenchError, "未切换模拟器"):
            CameraSource(0, factory=lambda _: cap)
        cap.release.assert_called_once()

    def test_camera_read_failure_does_not_return_frame(self):
        cap = Mock(); cap.isOpened.return_value = True; cap.read.return_value = (False, None)
        camera = CameraSource(0, factory=lambda _: cap)
        with self.assertRaisesRegex(BenchError, "未生成零数量或模拟帧"):
            camera.read()
        cap.release.assert_called_once()

    def test_transforms_preserve_raw(self):
        raw = fixture(); original = raw.copy()
        c = default_config(); c["mirror"] = True; c["rotation"] = 90
        result = transform_frame(raw, c)
        np.testing.assert_array_equal(raw, original)
        np.testing.assert_array_equal(result, cv2.flip(cv2.rotate(raw, cv2.ROTATE_90_CLOCKWISE), 1))

    def test_generated_disc_count(self):
        detector = BenchDetector(default_config())
        results = detector.detect(fixture())
        self.assertEqual([r.result.pill_count for r in results.values()], [2, 1, 3])
        self.assertTrue(all(r.status == "ok" for r in results.values()))

    def test_empty_usable_roi_is_valid_zero(self):
        results = BenchDetector(default_config()).detect(fixture((0, 0, 0)))
        self.assertEqual([r.result.pill_count for r in results.values()], [0, 0, 0])

    def test_white_background_is_not_valid_zero(self):
        results = BenchDetector(default_config()).detect(np.full((400,800,3), 240, np.uint8))
        self.assertTrue(all(r.status == "uncertain" and r.result is None for r in results.values()))

    def test_dark_frame_is_unknown(self):
        results = BenchDetector(default_config()).detect(np.zeros((400,800,3), np.uint8))
        self.assertTrue(all(r.status == "uncertain" and r.result is None for r in results.values()))

    def test_manual_occlusion_is_unknown(self):
        results = BenchDetector(default_config()).detect(fixture(), "手部遮挡")
        self.assertTrue(all(r.status == "uncertain" and r.result is None for r in results.values()))

    def test_tiny_roi_is_error(self):
        c = default_config(); c["slots"][0]["rect"] = [0.1,0.1,0.101,0.101]
        results = BenchDetector(c).detect(fixture())
        self.assertEqual(results["Morning"].status, "error")
        self.assertIsNone(results["Morning"].result)

    def test_missing_yolo_weights_no_download(self):
        c = default_config(); c["detector"]["backend"] = "yolo"
        with self.assertRaisesRegex(BenchError, "不会下载"):
            BenchDetector(c)

    def test_missing_cloud_key_no_fallback(self):
        c = default_config(); c["detector"]["backend"] = "roboflow"
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(BenchError):
            BenchDetector(c)

    def cloud_detector(self):
        c = default_config(); c["detector"]["backend"] = "roboflow"
        with patch.dict(os.environ, {"ROBOFLOW_API_KEY":"SECRET_DO_NOT_LOG"}):
            return BenchDetector(c)

    def test_cloud_error_does_not_use_opencv_or_log_key(self):
        detector = self.cloud_detector()
        with patch.dict(os.environ, {"ROBOFLOW_API_KEY":"SECRET_DO_NOT_LOG"}), \
             patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("https://x?api_key=SECRET_DO_NOT_LOG", 401, "no", {}, None)):
            result = detector.detect(fixture())
        self.assertTrue(all(r.status == "error" and r.result is None for r in result.values()))
        self.assertNotIn("SECRET_DO_NOT_LOG", " ".join(r.reason for r in result.values()))

    def test_cloud_malformed_response_is_failure(self):
        detector = self.cloud_detector()
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{}'
        with patch.dict(os.environ, {"ROBOFLOW_API_KEY":"key"}), patch("urllib.request.urlopen", return_value=response):
            results = detector.detect(fixture())
        self.assertTrue(all(r.status == "error" for r in results.values()))

    def test_cloud_request_timeout_and_no_prediction_cache(self):
        detector = self.cloud_detector()
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"predictions": []}'
        with patch.dict(os.environ, {"ROBOFLOW_API_KEY":"key"}), patch("urllib.request.urlopen", return_value=response) as call:
            detector.detect(fixture()); detector.detect(fixture())
            self.assertEqual(call.call_count, 2)
            self.assertEqual(call.call_args.kwargs["timeout"], 20)

    def test_cloud_centers_map_to_configured_rectangles(self):
        detector = self.cloud_detector()
        frame = fixture()
        predictions = []
        for slot in detector.config["slots"]:
            x1,y1,x2,y2 = pixel_rect(frame,slot)
            predictions.append({"x":(x1+x2)/2,"y":(y1+y2)/2,"width":20,"height":20,"class":"tablets","confidence":.9})
        with patch.object(detector,"_cloud",return_value=predictions):
            result = detector.detect(frame)
        self.assertEqual([r.result.pill_count for r in result.values()],[1,1,1])

    def test_non_pill_yolo_classes_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"fixture_weights.pt";path.write_bytes(b"not real weights")
            c=default_config();c["detector"].update(backend="yolo",yolo_model=str(path))
            fake=Mock();fake.names={0:"person",1:"car"}
            with patch("vision_bench.engine.LocalYoloPillDetector",return_value=fake), self.assertRaisesRegex(BenchError,"不匹配"):
                BenchDetector(c)

    def test_no_medication_state_machine_called(self):
        with patch("smart_pillbox_opencv.MedicationTracker.update", side_effect=AssertionError("not allowed")):
            BenchDetector(default_config()).detect(fixture((0,0,0)))


class DatasetAndMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = default_config()
        self.detector = BenchDetector(self.config)
        self.batch = Batch(self.root, self.config, self.detector.identity)

    def tearDown(self):
        self.temp.cleanup()

    def record(self, counts=None, meta=None, invalid=""):
        frame = fixture()
        return self.batch.record(frame, frame, counts or {"Morning":2,"Noon":1,"Evening":3},
                                 meta or metadata(), self.detector.detect(frame, invalid), self.detector)

    def test_ground_truth_and_prediction_association(self):
        rows = self.record({"Morning":1,"Noon":None,"Evening":3})
        self.assertEqual([(r["slot_id"],r["ground_truth"],r["raw_prediction"]) for r in rows],
                         [("Morning",1,2),("Noon",None,1),("Evening",3,3)])
        _, loaded = load_rows(self.batch.path)
        self.assertEqual(rows, loaded)

    def test_invalid_frame_count_is_null_not_zero(self):
        rows = self.record(invalid="遮挡")
        self.assertTrue(all(r["raw_prediction"] is None and r["event"] is None for r in rows))
        result = metrics(rows)
        self.assertEqual(result["failed_labelled"],3)
        self.assertEqual(result["exact_rate_all_labelled"],0)
        self.assertIsNone(result["mae_valid_only"])

    def test_mutating_detector_configuration_rejected(self):
        self.detector.config["mirror"] = True
        with self.assertRaisesRegex(BenchError, "新批次"):
            self.record()

    def test_rows_with_missing_slot_rejected(self):
        with self.assertRaises(BenchError): self.record({"Morning":2})

    def test_negative_label_rejected(self):
        with self.assertRaises(BenchError): self.record({"Morning":-1,"Noon":1,"Evening":3})

    def test_simulator_source_rejected(self):
        with self.assertRaises(BenchError): self.record(meta=metadata(source="simulator"))

    def test_image_integrity_check(self):
        rows = self.record()
        (self.batch.path / rows[0]["input_image"]).write_bytes(b"changed")
        with self.assertRaisesRegex(BenchError, "已改变"): export_batch(self.batch.path)

    def test_empty_dataset_does_not_make_accuracy(self):
        output, report = export_batch(self.batch.path)
        self.assertEqual(report["groups"], [])
        self.assertIsNone(report["overall_mixed_accuracy"])
        self.assertIsNone(metrics([])["coverage"])
        self.assertIsNone(metrics([])["exact_rate_all_labelled"])

    def test_unlabelled_samples_not_used_as_ground_truth(self):
        rows = self.record({"Morning":None,"Noon":None,"Evening":None})
        self.assertEqual(metrics(rows)["labelled"],0)
        self.assertIsNone(metrics(rows)["exact_rate_valid_only"])

    def test_failures_included_in_denominator(self):
        valid = self.record({"Morning":1,"Noon":None,"Evening":3})
        failed = self.record(invalid="遮挡")
        result = metrics(valid+failed)
        self.assertEqual(result["labelled"],5)
        self.assertEqual(result["exact_rate_all_labelled"],1/5)
        self.assertEqual(result["coverage"],2/5)
        self.assertEqual(result["mae_valid_only"],.5)

    def test_kinds_phases_sources_not_mixed(self):
        self.record(meta=metadata(sample_kind="simulant", phase="tuning"))
        self.record(meta=metadata(sample_kind="real_pill", phase="evaluation"))
        self.record(meta=metadata(sample_kind="test_fixture", phase="tuning", source="camera"))
        _, report = export_batch(self.batch.path)
        all_groups = [r for r in report["groups"] if r["dimension"] == "all"]
        self.assertEqual(len(all_groups),3)
        self.assertTrue(all(r["labelled"] == 3 for r in all_groups))

    def test_csv_bom_and_failure_gallery_escaping(self):
        self.record(meta=metadata(note="=HYPERLINK(\"x\")"), invalid="<script>alert(1)</script>")
        output, _ = export_batch(self.batch.path)
        raw = (output / "records.csv").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn("'=HYPERLINK", raw.decode("utf-8-sig"))
        page = (output / "failures.html").read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;",page)
        self.assertNotIn("<script>",page)

    def test_csv_formula_guard(self):
        self.assertEqual(csv_value(" =1+1"), "' =1+1")
        self.assertEqual(csv_value(0),0)
        self.assertEqual(csv_value(None),"")

    def test_template_contains_no_fabricated_predictions(self):
        path = self.root / "template.csv"
        write_template(path,self.config)
        import csv
        with path.open(encoding="utf-8-sig",newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r["ground_truth"] == "" and r["raw_prediction"] == "" for r in rows))


if __name__ == "__main__":
    unittest.main()
