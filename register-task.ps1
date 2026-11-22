# Registers the "Clipper Daily Clips" task: every day at 08:00 local time (IST).
# StartWhenAvailable = runs as soon as possible if the PC was off/asleep at 8:00.
$action   = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSScriptRoot\daily.ps1`"" -WorkingDirectory $PSScriptRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At "08:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Hours 12) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "Clipper Daily Clips" -Description "Cuts 50 clips from the top 20 trending US YouTube videos into clips\<date> in the project folder" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Get-ScheduledTaskInfo -TaskName "Clipper Daily Clips" | Select-Object NextRunTime
# To remove: Unregister-ScheduledTask -TaskName "Clipper Daily Clips" -Confirm:$false
