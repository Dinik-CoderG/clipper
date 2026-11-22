# Start Clipper at http://127.0.0.1:8000/youtube-clip-maker
# Optional: $env:ANTHROPIC_API_KEY = "sk-ant-..." to let Claude pick the moments
# Optional: $env:CLIPPER_WHISPER_MODEL = "small" (default "base"; larger = more accurate, slower)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
Set-Location server
..\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
