"""Tk smoke tests stay withdrawn, and never access a real camera."""
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from test_vision_bench import fixture
from vision_bench.config import BenchError, default_config
from vision_bench.engine import write_image
from vision_bench.gui import BenchApp


class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.temp.cleanup()
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.app = BenchApp(self.root, default_config(), Path(self.temp.name)/"config.json", Path(self.temp.name)/"runs")
        self.image_path = Path(self.temp.name)/"generated_fixture.png"
        write_image(self.image_path,fixture())
        with patch("vision_bench.gui.filedialog.askopenfilename", return_value=str(self.image_path)):
            self.app.open_image()

    def tearDown(self):
        if hasattr(self,"root"):
            self.app.close_camera()
            self.root.destroy()
        self.temp.cleanup()

    def wait_worker(self):
        deadline = time.monotonic()+10
        with patch("vision_bench.gui.messagebox.showerror", side_effect=AssertionError):
            while self.app.busy and time.monotonic()<deadline:
                self.root.update()
                time.sleep(.03)
        self.assertFalse(self.app.busy)

    def test_load_label_save_export_workflow(self):
        self.app.begin()
        self.assertTrue(all(str(w.cget("state")) == "disabled" for w in self.app.config_controls))
        for key,value in {"Morning":2,"Noon":1,"Evening":3}.items():
            self.app.counts[key].set(str(value))
        self.app.kind.set("软件测试夹具")
        self.app.fields["device"].set("software generated fixture")
        self.app.save_sample()
        self.wait_worker()
        self.assertIn("预测=2",self.app.result_text.get("1.0","end"))
        self.app.export()
        self.wait_worker()
        self.assertTrue((self.app.batch.path/"exports"/"records.csv").exists())
        with self.assertRaisesRegex(BenchError,"已保存"):
            self.app.save_sample()
        self.app.finish_end()
        self.assertTrue(all(str(w.cget("state")) != "disabled" for w in self.app.config_controls))

    def test_new_image_clears_previous_labels(self):
        self.app.counts["Morning"].set("5")
        with patch("vision_bench.gui.filedialog.askopenfilename", return_value=str(self.image_path)):
            self.app.open_image()
        self.assertTrue(all(v.get()=="" for v in self.app.counts.values()))

    def test_demo_keeps_labels_empty_and_kind_explicit(self):
        self.app.open_demo()
        self.assertEqual(self.app.kind.get(),"软件测试夹具")
        self.assertEqual(self.app.source,"image")
        self.assertTrue(all(v.get()=="" for v in self.app.counts.values()))
        self.app.begin()
        for key,value in {"Morning":2,"Noon":1,"Evening":3}.items():
            self.app.counts[key].set(str(value))
        self.app.kind.set("真实药片")
        with self.assertRaisesRegex(BenchError,"软件测试夹具"):
            self.app.save_sample()
        self.app.kind.set("软件测试夹具")
        self.app.save_sample()
        self.wait_worker()
        self.assertIn("预测=2",self.app.result_text.get("1.0","end"))

    def test_demo_respects_mirror_and_rotation(self):
        self.app.config["mirror"]=True;self.app.mirror.set(True)
        self.app.config["rotation"]=90;self.app.rotation.set("90")
        self.app.open_demo()
        self.app.begin()
        observations=self.app.detector.detect(self.app.frame)
        self.assertEqual([r.result.pill_count for r in observations.values()],[2,1,3])

    def test_begin_requires_frozen_image(self):
        self.app.frozen=False
        with self.assertRaisesRegex(BenchError,"定格"):
            self.app.begin()

    def test_camera_open_failure_does_not_use_simulator(self):
        with patch("vision_bench.gui.CameraSource",side_effect=BenchError("camera unavailable")):
            with self.assertRaisesRegex(BenchError,"camera unavailable"):
                self.app.open_camera()
        self.assertIsNone(self.app.camera)
        self.assertIsNone(self.app.frame)
        self.assertIsNone(self.app.raw)

    def test_manual_quality_records_unknown(self):
        self.app.begin()
        self.app.fields["device"].set("software fixture")
        self.app.kind.set("软件测试夹具")
        for v in self.app.counts.values():
            v.set("1")
        self.app.quality.set("手部遮挡")
        self.app.save_sample()
        self.wait_worker()
        self.assertIn("预测=无法判断", self.app.result_text.get("1.0","end"))


if __name__ == "__main__":
    unittest.main()
