param(
    [Parameter(Mandatory=$true)][string]$Project,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [int]$TimeoutSeconds = 600
)
$ErrorActionPreference = 'Stop'
$auditRoot = Split-Path -Parent $PSScriptRoot
$auditProject = (Resolve-Path -LiteralPath $Project).Path
$auditOut = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $auditOut) { throw 'Fresh audit destination required' }
if ($TimeoutSeconds -lt 30 -or $TimeoutSeconds -gt 900) { throw 'Timeout must be 30..900 seconds' }
$auditBeforeHash = (Get-FileHash -LiteralPath $auditProject -Algorithm SHA256).Hash
$auditFree = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 1KB
if ($auditFree -lt 1.5GB) { throw "Postprocessing admission denied: $([math]::Round($auditFree/1GB,2)) GiB available" }
New-Item -ItemType Directory -Path $auditOut | Out-Null
$auditPython = Join-Path $auditRoot '.venv-hfss\Scripts\python.exe'
$auditScript = Join-Path $PSScriptRoot 'export_power_budget_revision06.py'
$auditChildOut = Join-Path $auditOut 'power'
$auditArgs = @($auditScript, '--project', $auditProject, '--out', $auditChildOut,
               '--minimum-free-memory-gib', '1.5')
# Paths are individually quoted for Start-Process's Windows command-line joining.
if (($auditArgs | Where-Object { $_.Contains('"') }).Count) { throw 'Quotes in arguments are unsupported' }
$auditArgs = @($auditArgs | ForEach-Object { '"' + $_ + '"' })
$auditProcess = Start-Process -FilePath $auditPython -ArgumentList $auditArgs -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $auditOut 'stdout.log') `
    -RedirectStandardError (Join-Path $auditOut 'stderr.log') -WorkingDirectory $auditRoot
$auditClock = [Diagnostics.Stopwatch]::StartNew()
$auditOwned = @{}
$auditRootIdentity = Get-CimInstance Win32_Process -Filter "ProcessId=$($auditProcess.Id)"
if ($auditRootIdentity) { $auditOwned[[uint32]$auditRootIdentity.ProcessId] = $auditRootIdentity.CreationDate }
$auditPeak = 0L
$auditMinFree = $auditFree
$auditReason = $null
$auditReturnCode = $null
try {
    while (-not $auditProcess.HasExited) {
        $auditSnapshot = @(Get-CimInstance Win32_Process)
        $auditParents = @($auditSnapshot | Where-Object {
            $auditOwned.ContainsKey([uint32]$_.ProcessId) -and $auditOwned[[uint32]$_.ProcessId] -eq $_.CreationDate
        } | ForEach-Object { [uint32]$_.ProcessId })
        for ($auditDepth = 0; $auditDepth -lt 8; $auditDepth++) {
            $auditNew = @($auditSnapshot | Where-Object {
                $auditParents -contains $_.ParentProcessId
            })
            foreach ($auditItem in $auditNew) {
                if (-not $auditOwned.ContainsKey([uint32]$auditItem.ProcessId)) {
                    $auditOwned[[uint32]$auditItem.ProcessId] = $auditItem.CreationDate
                }
            }
            $auditParents = @($auditSnapshot | Where-Object {
                $auditOwned.ContainsKey([uint32]$_.ProcessId) -and $auditOwned[[uint32]$_.ProcessId] -eq $_.CreationDate
            } | ForEach-Object { [uint32]$_.ProcessId })
        }
        $auditCurrent = @($auditSnapshot | Where-Object {
            $auditOwned.ContainsKey([uint32]$_.ProcessId) -and $auditOwned[[uint32]$_.ProcessId] -eq $_.CreationDate
        })
        $auditWorking = [long](($auditCurrent | Measure-Object -Property WorkingSetSize -Sum).Sum)
        $auditFree = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 1KB
        $auditPeak = [math]::Max($auditPeak, $auditWorking)
        $auditMinFree = [math]::Min($auditMinFree, $auditFree)
        if ($auditFree -lt 512MB) { $auditReason = 'host_memory_floor' }
        if ($auditWorking -gt 1.25GB) { $auditReason = 'owned_working_set_cap' }
        if ($auditClock.Elapsed.TotalSeconds -gt $TimeoutSeconds) { $auditReason = 'wall_time_limit' }
        if ($auditReason) { break }
        Start-Sleep -Seconds 2
        $auditProcess.Refresh()
    }
    if (-not $auditReason) { $auditProcess.WaitForExit(); $auditReturnCode = $auditProcess.ExitCode }
} finally {
    # Stop only the exact descendants observed from this launched Python root.
    # Creation times prevent a reused PID from identifying an unrelated process.
    $auditRemaining = @(Get-CimInstance Win32_Process | Where-Object {
        $auditOwned.ContainsKey([uint32]$_.ProcessId) -and $auditOwned[[uint32]$_.ProcessId] -eq $_.CreationDate
    })
    foreach ($auditItem in ($auditRemaining | Sort-Object ProcessId -Descending)) {
        Stop-Process -Id $auditItem.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $auditReport = [ordered]@{
        scope = 'Read-only existing-solution diagnostic; no adaptive solve'
        project = $auditProject
        root_pid = $auditProcess.Id
        owned_process_ids = @($auditOwned.Keys)
        exit_code = $auditReturnCode
        interruption_reason = $auditReason
        maximum_working_set_gib = $auditPeak / 1GB
        minimum_available_memory_gib = $auditMinFree / 1GB
        working_set_cap_gib = 1.25
        available_memory_floor_gib = 0.5
        elapsed_seconds = $auditClock.Elapsed.TotalSeconds
        source_sha256_before = $auditBeforeHash
        source_sha256_after = (Get-FileHash -LiteralPath $auditProject -Algorithm SHA256).Hash
        efficiency_corrected = $false
    }
    $auditReport | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $auditOut 'resource_guard.json') -Encoding utf8
    $auditReport | ConvertTo-Json -Compress
}
if ($auditReason -or $auditReturnCode -ne 0) { exit 2 }
