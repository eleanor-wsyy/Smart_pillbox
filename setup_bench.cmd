@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Python 3.10+ is required. Install Python with Tkinter and ensure python works in your terminal.
    echo Then run this setup again. See docs\vision_bench_guide.md.
    pause
    exit /b 2
)
python -m venv .venv-bench
if errorlevel 1 goto failed
".venv-bench\Scripts\python.exe" -m pip install -r requirements-bench.txt
if errorlevel 1 goto failed
".venv-bench\Scripts\python.exe" -c "import cv2, numpy, PIL, tkinter; print('Dependencies ready.')"
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click start_bench.cmd to open the tool.
pause
exit /b 0
:failed
echo.
echo Setup failed. Keep the error above and consult docs\vision_bench_guide.md.
echo No system security settings were changed.
pause
exit /b 2
