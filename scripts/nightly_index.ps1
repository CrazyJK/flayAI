# flayAI 야간 인덱싱 (AI_PLAN.md §9.4)
#
# 절차:
#   1) LLM unload (옵션, 메모리 회수)
#   2) translate (신규 cursor 분량만)
#   3) embed_text (videos 컬렉션 incremental)
#   4) (주 1회) 이미지/얼굴/OCR 인덱싱
#   5) reload (필요 시)
#   6) backup
#
# Windows Task Scheduler 등록 예:
#   schtasks /Create /SC DAILY /ST 03:00 /TN flayAI-Nightly `
#            /TR "powershell.exe -ExecutionPolicy Bypass -File C:\kamoru\Workspace\git\flayAI\scripts\nightly_index.ps1"

[CmdletBinding()]
param(
    [switch]$FullWeekly,            # 강제 주간 풀
    [switch]$SkipBackup,
    [switch]$SkipOllamaUnload,
    [string]$LogDir = "logs"
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $LogDir "nightly-$stamp.log"

function Log($msg) {
    $line = "[$(Get-Date -Format HH:mm:ss)] $msg"
    Write-Host $line
    Add-Content -Path $log -Value $line
}

Log "==== nightly start ===="

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Log "ERR python venv missing"; exit 2 }

$weekly = $FullWeekly.IsPresent -or ((Get-Date).DayOfWeek -eq [DayOfWeek]::Sunday)
Log "weekly=$weekly"

# 1) Ollama unload (GPU 회수)
if (-not $SkipOllamaUnload) {
    Log "[1/6] ollama unload"
    try {
        # 모든 로드 모델 unload
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

# 2) translate (incremental 기본 — 신규/누락 만)
Log "[2/6] translate"
& $py -m packages.indexer.cli translate 2>&1 | Tee-Object -Append $log | Out-Null
Log "    translate exit=$LASTEXITCODE"

# 3) embed_text (incremental 기본)
Log "[3/6] embed videos"
& $py -m packages.indexer.cli embed 2>&1 | Tee-Object -Append $log | Out-Null
Log "    embed exit=$LASTEXITCODE"

# 4) 주 1회 이미지/얼굴/OCR (incremental 기본)
if ($weekly) {
    Log "[4/6] (weekly) embed-clip"
    & $py -m packages.indexer.cli embed-clip 2>&1 | Tee-Object -Append $log | Out-Null

    Log "[4/6] (weekly) extract-faces"
    & $py -m packages.indexer.cli extract-faces 2>&1 | Tee-Object -Append $log | Out-Null

    Log "[4/6] (weekly) ocr-posters"
    & $py -m packages.indexer.cli ocr-posters 2>&1 | Tee-Object -Append $log | Out-Null

    Log "[4/6] (weekly) cluster-faces"
    & $py -m packages.indexer.cli cluster-faces 2>&1 | Tee-Object -Append $log | Out-Null
} else {
    Log "[4/6] (skipped — daily)"
}

# 5) reload — FastAPI 가 lazy load 이므로 별도 작업 없음
Log "[5/6] reload: noop (lazy)"

# 6) 백업
if (-not $SkipBackup) {
    Log "[6/6] backup"
    & "$PSScriptRoot\backup.ps1" 2>&1 | Tee-Object -Append $log | Out-Null
    Log "    backup exit=$LASTEXITCODE"
} else {
    Log "[6/6] backup skipped"
}

Log "==== nightly done ===="
