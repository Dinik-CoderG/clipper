# Daily clip run (called by Windows Task Scheduler at 08:00 IST). Output: clips\<date>\ in the project folder
Set-Location "$PSScriptRoot\server"
& "$PSScriptRoot\.venv\Scripts\python.exe" daily.py @args
exit $LASTEXITCODE
