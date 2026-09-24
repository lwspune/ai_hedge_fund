# Registers the infra refresh tasks in Windows Task Scheduler (current user, runs while logged on).
#   powershell -ExecutionPolicy Bypass -File scripts\register_schedule.ps1
# StartWhenAvailable: a run missed while the PC was off/asleep fires at the next opportunity.
$ErrorActionPreference = 'Stop'
$root   = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
$script = Join-Path $root 'scripts\scheduled_refresh.py'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 8) -MultipleInstances IgnoreNew

$tasks = @(
    @{ Name = 'MarketIntel-Daily';  Mode = 'daily';
       Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '20:30' },
    @{ Name = 'MarketIntel-Weekly'; Mode = 'weekly';
       Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '10:00' }
)
foreach ($t in $tasks) {
    $action = New-ScheduledTaskAction -Execute $python -Argument "`"$script`" $($t.Mode)" -WorkingDirectory $root
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $t.Trigger -Settings $settings `
        -Description "Market-intel infra refresh ($($t.Mode)); logs in $root\logs" -Force | Out-Null
    Write-Output "registered $($t.Name)"
}
