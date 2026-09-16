param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [ValidateSet(15,20)][int]$BoundaryMeshMm = 15
)
$ErrorActionPreference = 'Stop'
$meshRoot = Split-Path -Parent $PSScriptRoot
$meshOut = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $meshOut) { throw 'Fresh refinement directory required' }
$meshFree = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 1KB
if ($meshFree -lt 3GB) { throw "Refinement admission denied: $([math]::Round($meshFree/1GB,2)) GiB available" }
if ((Get-Item (Split-Path -Qualifier $meshOut)).PSDrive.Free -lt 10GB) { throw 'At least 10 GiB output-drive space required' }
New-Item -ItemType Directory -Path $meshOut | Out-Null
$meshProject = Join-Path $meshOut "Velocity_Connect_R06_Radiation_B$BoundaryMeshMm.aedt"
$meshPython = Join-Path $meshRoot '.venv-hfss\Scripts\python.exe'
$meshScript = Join-Path $PSScriptRoot 'build_n78_v2_dualport.py'
$meshArgs = @($meshScript, '--output', $meshProject, '--aedt-version', '2025.2',
    '--aedt-edition', 'student', '--solve', '--non-graphical', '--cores', '2',
    '--finite-conductivity', '--open-boundary', 'Radiation', '--polarization-layout', 'dual-slant',
    '--slant-angle-deg', '45', '--height', '24', '--top-w', '16', '--base-w', '22',
    '--neck-w', '4', '--shoulder-h', '5', '--feed-gap', '0.8', '--blade-t', '0.5',
    '--separation', '160', '--ground-x', '360', '--ground-y', '180', '--ground-t', '1',
    '--radome', '--radome-layout', 'split', '--radome-permittivity', '1.8',
    '--radome-loss-tangent', '0.001', '--radome-wall-mm', '1', '--radome-air-gap-mm', '15',
    '--maximum-passes', '18', '--minimum-converged-passes', '2', '--max-delta-s', '0.005',
    '--percent-refinement', '10', '--basis-order', '1', '--absorbing-boundary-mesh-mm', "$BoundaryMeshMm",
    '--far-field-step-deg', '2.5')
if (($meshArgs | Where-Object { $_.Contains('"') }).Count) { throw 'Quotes in arguments are unsupported' }
$meshArgs | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $meshOut 'command.json') -Encoding utf8
$meshQuoted = @($meshArgs | ForEach-Object { '"' + $_ + '"' })
$meshProcess = Start-Process -FilePath $meshPython -ArgumentList $meshQuoted -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $meshOut 'stdout.log') `
    -RedirectStandardError (Join-Path $meshOut 'stderr.log') -WorkingDirectory $meshRoot
$meshTimer = [Diagnostics.Stopwatch]::StartNew()
$meshOwned = @{}
$meshRootIdentity = Get-CimInstance Win32_Process -Filter "ProcessId=$($meshProcess.Id)"
if ($meshRootIdentity) { $meshOwned[[uint32]$meshRootIdentity.ProcessId] = $meshRootIdentity.CreationDate }
$meshPeak = 0L
$meshMinimum = $meshFree
$meshReason = $null
$meshExit = $null
try {
    while (-not $meshProcess.HasExited) {
        $meshSnapshot = @(Get-CimInstance Win32_Process)
        $meshParents = @($meshSnapshot | Where-Object {
            $meshOwned.ContainsKey([uint32]$_.ProcessId) -and $meshOwned[[uint32]$_.ProcessId] -eq $_.CreationDate
        } | ForEach-Object { [uint32]$_.ProcessId })
        for ($meshDepth = 0; $meshDepth -lt 8; $meshDepth++) {
            foreach ($meshItem in @($meshSnapshot | Where-Object {
                $meshParents -contains $_.ParentProcessId
            })) {
                if (-not $meshOwned.ContainsKey([uint32]$meshItem.ProcessId)) {
                    $meshOwned[[uint32]$meshItem.ProcessId] = $meshItem.CreationDate
                }
            }
            $meshParents = @($meshSnapshot | Where-Object {
                $meshOwned.ContainsKey([uint32]$_.ProcessId) -and $meshOwned[[uint32]$_.ProcessId] -eq $_.CreationDate
            } | ForEach-Object { [uint32]$_.ProcessId })
        }
        $meshCurrent = @($meshSnapshot | Where-Object {
            $meshOwned.ContainsKey([uint32]$_.ProcessId) -and $meshOwned[[uint32]$_.ProcessId] -eq $_.CreationDate
        })
        $meshWorking = [long](($meshCurrent | Measure-Object -Property WorkingSetSize -Sum).Sum)
        $meshFree = (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory * 1KB
        $meshPeak = [math]::Max($meshPeak, $meshWorking)
        $meshMinimum = [math]::Min($meshMinimum, $meshFree)
        if ($meshFree -lt 512MB) { $meshReason = 'host_memory_floor' }
        if ($meshWorking -gt 2.75GB) { $meshReason = 'owned_working_set_cap' }
        if ($meshTimer.Elapsed.TotalSeconds -gt 900) { $meshReason = 'wall_time_limit' }
        if (Test-Path -LiteralPath (Join-Path $meshOut 'STOP_REQUESTED')) { $meshReason = 'requested_stop' }
        if ($meshReason) { break }
        Start-Sleep -Seconds 2
        $meshProcess.Refresh()
    }
    if (-not $meshReason) { $meshProcess.WaitForExit(); $meshExit = $meshProcess.ExitCode }
} finally {
    # An interrupted run is retained and excluded, never resumed or reported solved.
    foreach ($meshItem in @(Get-CimInstance Win32_Process | Where-Object {
        $meshOwned.ContainsKey([uint32]$_.ProcessId) -and $meshOwned[[uint32]$_.ProcessId] -eq $_.CreationDate
    } | Sort-Object ProcessId -Descending)) {
        Stop-Process -Id $meshItem.ProcessId -Force -ErrorAction SilentlyContinue
    }
    $meshReport = [ordered]@{project=$meshProject; root_pid=$meshProcess.Id; owned_pids=@($meshOwned.Keys)
        exit_code=$meshExit; interruption_reason=$meshReason; elapsed_seconds=$meshTimer.Elapsed.TotalSeconds
        maximum_working_set_gib=$meshPeak/1GB; minimum_available_memory_gib=$meshMinimum/1GB
        working_set_cap_gib=2.75; host_memory_floor_gib=0.5; timeout_seconds=900
        changed_factor="Radiation-boundary mesh maximum edge 25 mm to $BoundaryMeshMm mm only"
        physical_acceptance=$false}
    $meshReport | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $meshOut 'resource_guard.json') -Encoding utf8
    $meshReport | ConvertTo-Json -Compress
}
if ($meshReason -or $meshExit -ne 0) { exit 2 }
