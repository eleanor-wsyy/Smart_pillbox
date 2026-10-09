@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if exist ".venv-bench\Scripts\python.exe" (
    ".venv-bench\Scripts\python.exe" bench_tool.py gui
) else (
    python bench_tool.py gui
)
if errorlevel 1 (
    echo.
    echo Launch failed. See docs\vision_bench_guide.md for setup instructions.
    pause
)
