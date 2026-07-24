# Interlock mask sweep driver for the CGC ESI controller (firmware 1-10).
#
# Walks all 256 combinations of HvPsInterlockEnable x HeatControlInterlockEnable
# (config slots 10..265 in COM-ESI-ILOCK-SWEEP-1/2/3.cfg). For each combo:
#   1. uploads the right sweep file when needed (-XL),
#   2. activates the combo slot (-xcN),
#   3. waits while you physically open the interlock loop and observe,
#   4. records your verdict to interlock_sweep_results.csv,
#   5. switches back to slot 1 = Off, waits for you to close the box.
#
# Resume is automatic: already-recorded configs are skipped on restart.
#
# Usage (from this folder):
#   powershell -ExecutionPolicy Bypass -File .\interlock_sweep.ps1
#   powershell -ExecutionPolicy Bypass -File .\interlock_sweep.ps1 -Port 14 -StartConfig 42

param(
    [int]$Port = 14,
    [int]$StartConfig = 10
)

$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$exe = Join-Path $dir 'ESI-Controller.exe'
$log = Join-Path $dir 'interlock_sweep_results.csv'

if (-not (Test-Path $exe)) { Write-Host "ESI-Controller.exe not found in $dir" -ForegroundColor Red; exit 1 }

function MaskStr([int]$m) {
    (0..3 | ForEach-Object { if (($m -shr $_) -band 1) { 'Y' } else { 'N' } }) -join ','
}

# Build the combo table — MUST match the generator: outer loop = heat mask,
# inner loop = HVPS mask, config number = 10 + ht*16 + hv.
$combos = foreach ($ht in 0..15) { foreach ($hv in 0..15) {
    $n = $ht * 16 + $hv
    [pscustomobject]@{
        Config = 10 + $n
        Hv     = MaskStr $hv
        Ht     = MaskStr $ht
        File   = 'COM-ESI-ILOCK-SWEEP-{0}.cfg' -f ([math]::Floor($n / 100) + 1)
    }
}}

# Resume: skip configs already in the log.
if (-not (Test-Path $log)) {
    'timestamp,config,hvps_mask,heat_mask,result' | Out-File $log -Encoding ascii
}
$done = @{}
Import-Csv $log | ForEach-Object { $done[[int]$_.config] = $_.result }

function Run-Esi([string[]]$esiArgs) {
    & $exe @esiArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ESI-Controller exited with code $LASTEXITCODE (args: $($esiArgs -join ' '))" -ForegroundColor Red
    }
}

Push-Location $dir
try {
    $remaining = @($combos | Where-Object { $_.Config -ge $StartConfig -and -not $done.ContainsKey($_.Config) })
    Write-Host ("Interlock sweep: {0} of 256 combos remaining. Log: {1}" -f $remaining.Count, $log) -ForegroundColor Cyan
    Write-Host "Verdict keys: [g]=GOAL (HVPS off, heater stays on)  [x]=heater died too  [n]=nothing tripped  [o]=other (note)  [s]=skip  [q]=quit`n"

    $lastFile = ''
    foreach ($c in $remaining) {
        if ($c.File -ne $lastFile) {
            Write-Host ">> Uploading $($c.File) to device..." -ForegroundColor Cyan
            Run-Esi @("$Port", '-$', '-XL', $c.File, '-t')
            $lastFile = $c.File
        }

        Write-Host ''
        Write-Host ("=== Config {0}   HvPs={1}   HeatControl={2} ===" -f $c.Config, $c.Hv, $c.Ht) -ForegroundColor Yellow
        Run-Esi @("$Port", '-$', ('-xc{0}' -f $c.Config), '-t')
        Write-Host 'Config active. OPEN the interlock loop now and observe HVPS + heater.'

        $r = ''
        while ($r -notin @('g', 'x', 'n', 'o', 's', 'q')) {
            $r = (Read-Host 'Verdict [g/x/n/o/s/q]').Trim().ToLower()
        }
        if ($r -eq 'q') { break }

        $note = ''
        if ($r -eq 'o') { $note = (Read-Host 'Short note') -replace ',', ';' }
        $result = if ($note) { "o: $note" } else { $r }
        '{0},{1},{2},{3},{4}' -f (Get-Date -Format s), $c.Config, ($c.Hv -replace ','), ($c.Ht -replace ','), $result |
            Add-Content $log -Encoding ascii

        if ($r -eq 'g') {
            Write-Host ("GOAL combo found: HvPsInterlockEnable={0}  HeatControlInterlockEnable={1} (config {2})" -f $c.Hv, $c.Ht, $c.Config) -ForegroundColor Green
        }

        Write-Host '>> Back to Off (config 1)...'
        Run-Esi @("$Port", '-$', '-xc1', '-t')
        Read-Host 'CLOSE the interlock loop again, then press Enter for the next combo'
    }
}
finally {
    Pop-Location
}

Write-Host "`nSweep session ended. Results so far:" -ForegroundColor Cyan
Import-Csv $log | Where-Object { $_.result -eq 'g' } | Format-Table config, hvps_mask, heat_mask -AutoSize
Write-Host "Full log: $log"
