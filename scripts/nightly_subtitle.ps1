# flayAI nightly subtitle drain
#
# Processes the subtitle request queue (subtitle_jobs) while idle/asleep.
# Each job: opus -> faster-whisper (JP, VAD) -> translate (JP->KO) -> <stem>.srt sidecar.
# Incremental and idempotent: transcripts are cached, existing fan-subs are skipped.
#
# ASCII only (CLAUDE.md: no non-ASCII in .ps1/.bat/.cmd).
#
# Register with Windows Task Scheduler (run after nightly_index so they do not
# share the GPU at the same time), e.g.:
#   schtasks /Create /SC DAILY /ST 04:30 /TN flayAI-Subtitle `
#            /TR "powershell.exe -ExecutionPolicy Bypass -File C:\kamoru\Workspace\git\flayAI\scripts\nightly_subtitle.ps1"

[CmdletBinding()]
param(
    [switch]$SkipOllamaUnload,
    [string]$LogDir = "logs"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $LogDir "subtitle-$stamp.log"

function Log($msg) {
    $line = "[$(Get-Date -Format HH:mm:ss)] $msg"
    Write-Host $line
    Add-Content -Path $log -Value $line
}

Log "==== subtitle drain start ===="

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Log "ERR python venv missing"; exit 2 }

# Free GPU: unload any loaded Ollama models (whisper + NLLB want the VRAM).
if (-not $SkipOllamaUnload) {
    Log "ollama unload"
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/ps" -TimeoutSec 5 |
            Select-Object -ExpandProperty models -ErrorAction SilentlyContinue |
            ForEach-Object {
                $body = @{ model = $_.name; keep_alive = 0 } | ConvertTo-Json
                Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/generate" `
                                  -Method Post -Body $body -ContentType "application/json" `
                                  -TimeoutSec 30 | Out-Null
                Log "    unloaded $($_.name)"
            }
    } catch { Log "    ollama unload skipped: $_" }
}

Log "drain queue"
& $py -m packages.subtitler.cli drain 2>&1 | Tee-Object -Append $log | Out-Null
Log "    drain exit=$LASTEXITCODE"

Log "==== subtitle drain done ===="
