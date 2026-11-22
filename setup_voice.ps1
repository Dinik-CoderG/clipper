# One-time setup for the voice tools: a separate Python environment for Chatterbox (MIT licence), so its
# dependencies (its own PyTorch version) can't break the main .venv.
# Run from the project folder:   powershell -ExecutionPolicy Bypass -File setup_voice.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "Python launcher 'py' not found. Install Python 3.11 from python.org." }
& py -3.11 --version
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 is required (Chatterbox is tested on 3.11). Install it from python.org." }

if (-not (Test-Path ".venv-voice")) { & py -3.11 -m venv .venv-voice }
$py = ".\.venv-voice\Scripts\python.exe"
& $py -m pip install --upgrade pip
# CUDA build of the PyTorch version Chatterbox pins; the default PyPI wheel would be CPU-only on Windows.
& $py -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
& $py -m pip install chatterbox-tts
& $py -c "import torch; print('CUDA available:', torch.cuda.is_available())"
New-Item -ItemType Directory -Force likeness | Out-Null
Write-Host "`nDone. Next: record 15-30 s of yourself talking naturally (quiet room, phone close), then:"
Write-Host "  .venv\Scripts\python.exe -P reels\voice.py enroll <your-recording>"
