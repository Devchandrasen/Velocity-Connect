param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9][a-z0-9_]{0,40}$')]
    [string]$InvocationName
)
$ErrorActionPreference = 'Stop'
$campaignOut = 'W:\Velocity-Connect-Revision06\campaign-20260907-v1'
$campaignWslOut = '/mnt/w/Velocity-Connect-Revision06/campaign-20260907-v1'
$campaignRuntime = "$campaignWslOut/runtime/scripts/run_vehcom_revision06.py"
$campaignInvocation = Join-Path (Join-Path $campaignOut 'invocations') $InvocationName
if (Test-Path -LiteralPath $campaignInvocation) { throw 'Fresh invocation name required; logs cannot be overwritten' }
if (-not (Test-Path -LiteralPath (Join-Path $campaignOut 'revision06.json'))) { throw 'Frozen plan is missing' }
if (Test-Path -LiteralPath (Join-Path $campaignOut 'STOP')) { throw 'Campaign STOP exists; do not remove it automatically' }

# The frozen runner rechecks provenance, OS locks, RAM and disk before EVERY row.
# This wrapper adds no scientific treatments and never retries terminal rows.
$campaignAdmissionText = & wsl.exe -d Ubuntu-22.04 -u codex -- python3 -B $campaignRuntime admit `
    --out $campaignWslOut --profiles principal channel-sensitivity
if ($LASTEXITCODE -ne 0) { throw 'Frozen-runtime admission failed' }
$campaignAdmission = ($campaignAdmissionText -join "`n") | ConvertFrom-Json
foreach ($campaignFamily in @('principal','channel-sensitivity')) {
    if (-not $campaignAdmission.admission.$campaignFamily.admitted) {
        throw "Admission denied for $campaignFamily; no process started"
    }
}
New-Item -ItemType Directory -Path $campaignInvocation | Out-Null
$campaignArgs = @('-d','Ubuntu-22.04','-u','codex','--','python3','-B',$campaignRuntime,
    'run','--out',$campaignWslOut,'--execute','--profiles','principal','channel-sensitivity',
    '--max-rows','320','--wall-seconds','43200')
# WSL's native option parser does not accept a quoted initial -d as an option.
# All frozen arguments have no spaces; reject future changes requiring escaping.
if ($campaignArgs | Where-Object { $_ -match '[\s"\r\n]' }) { throw 'Unexpected argument requiring native WSL escaping' }
$campaignProcess = Start-Process -FilePath 'C:\Windows\System32\wsl.exe' -ArgumentList ($campaignArgs -join ' ') `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $campaignInvocation 'stdout.log') `
    -RedirectStandardError (Join-Path $campaignInvocation 'stderr.log')
$campaignRecord = [ordered]@{
    started_utc=[DateTime]::UtcNow.ToString('o'); windows_wsl_pid=$campaignProcess.Id
    process_start_utc=$campaignProcess.StartTime.ToUniversalTime().ToString('o')
    arguments=$campaignArgs; admission=$campaignAdmission
    expected_total_rows=680; invocation_maximum_row_starts=320
    selected_profiles=@('principal','channel-sensitivity'); load_started=$false
    invocation_wall_budget_seconds=43200; statistics=$null
    stop_file=(Join-Path $campaignOut 'STOP')
    evidence_boundary='Started is not completed or analyzed. No calibrated moving EM coupling.'
}
$campaignRecord | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $campaignInvocation 'launch.json') -Encoding utf8
$campaignRecord | ConvertTo-Json -Depth 12 -Compress
