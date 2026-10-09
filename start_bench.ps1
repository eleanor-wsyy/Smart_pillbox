$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv-bench\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host '未找到台架测试环境，请先按 docs/vision_bench_guide.md 安装依赖。'
    Write-Host 'python -m venv .venv-bench'
    Write-Host '.\.venv-bench\Scripts\python.exe -m pip install -r requirements-bench.txt'
    exit 2
}
& $python 'bench_tool.py' 'gui'
exit $LASTEXITCODE
