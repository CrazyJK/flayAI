# flayAI 백업 스크립트 (AI_PLAN.md §9.2)
#
# 산출물:
#   $dst\flay.db                 SQLite VACUUM INTO
#   $dst\qdrant\<collection>\    Qdrant snapshot 파일
#   $dst\state.json, config.yaml
#   $dst\manifest.json           메타 (timestamp, sizes)
#
# 보존 정책: 최근 7개 일일 백업 + 매주 일요일 1개 (보관 무한)
#
# 사용:
#   .\scripts\backup.ps1                    # 기본 K:\Backup\flayAI
#   .\scripts\backup.ps1 -DstRoot D:\Backup
#   .\scripts\backup.ps1 -SkipQdrant        # SQLite 만

[CmdletBinding()]
param(
    [string]$DstRoot = "K:\Backup\flayAI",
    [string]$QdrantUrl = "http://127.0.0.1:6333",
    [string[]]$Collections = @("videos", "posters_clip", "faces", "poster_ocr"),
    [switch]$SkipQdrant,
    [int]$KeepDaily = 7
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ts  = Get-Date -Format "yyyyMMdd-HHmmss"
$dst = Join-Path $DstRoot $ts
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Write-Host "[backup] dst=$dst"

# ---- 1) SQLite VACUUM INTO ---------------------------------------------
$srcDb = Join-Path $root "data\sqlite\flay.db"
$dstDb = Join-Path $dst "flay.db"
if (Test-Path $srcDb) {
    Write-Host "[backup] sqlite VACUUM INTO ..."
    & ".\.venv\Scripts\python.exe" -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute(\"VACUUM INTO '\" + sys.argv[2].replace('\\','/') + \"'\"); c.close()" $srcDb $dstDb
    $sz = (Get-Item $dstDb).Length
    Write-Host ("[backup] sqlite OK  {0:N0} bytes" -f $sz)
} else {
    Write-Warning "[backup] sqlite missing: $srcDb"
}

# ---- 2) Qdrant snapshots -----------------------------------------------
$snapDir = Join-Path $dst "qdrant"
if (-not $SkipQdrant) {
    New-Item -ItemType Directory -Path $snapDir -Force | Out-Null
    foreach ($col in $Collections) {
        try {
            Write-Host "[backup] qdrant snapshot $col ..."
            $resp = Invoke-RestMethod -Uri "$QdrantUrl/collections/$col/snapshots" `
                                      -Method Post -TimeoutSec 600
            $name = $resp.result.name
            if (-not $name) { throw "no snapshot name returned" }
            $outFile = Join-Path $snapDir "$col-$name"
            Invoke-WebRequest -Uri "$QdrantUrl/collections/$col/snapshots/$name" `
                              -OutFile $outFile -TimeoutSec 1200
            $sz = (Get-Item $outFile).Length
            Write-Host ("[backup]   {0}: {1:N0} bytes" -f $col, $sz)
            # 원격 snapshot 정리
            Invoke-RestMethod -Uri "$QdrantUrl/collections/$col/snapshots/$name" `
                              -Method Delete -TimeoutSec 60 | Out-Null
        } catch {
            Write-Warning "[backup] qdrant $col failed: $_"
        }
    }
}

# ---- 3) 설정/state ------------------------------------------------------
foreach ($f in @("config.yaml", "data\state.json")) {
    $src = Join-Path $root $f
    if (Test-Path $src) {
        Copy-Item $src (Join-Path $dst (Split-Path -Leaf $f)) -Force
    }
}

# ---- 4) manifest --------------------------------------------------------
$manifest = @{
    timestamp = (Get-Date).ToString("o")
    host = $env:COMPUTERNAME
    flayai_root = $root
    sqlite_bytes = if (Test-Path $dstDb) { (Get-Item $dstDb).Length } else { 0 }
    qdrant_collections = $Collections
    qdrant_files = if (Test-Path $snapDir) {
        Get-ChildItem $snapDir -File | ForEach-Object { @{ name = $_.Name; bytes = $_.Length } }
    } else { @() }
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $dst "manifest.json")

# ---- 5) 보존 회전 (daily + 매주 일요일 보관) ----------------------------
Write-Host "[backup] rotate (keep daily=$KeepDaily, weekly=Sunday)"
$all = Get-ChildItem -Directory $DstRoot |
       Where-Object { $_.Name -match '^\d{8}-\d{6}$' } |
       Sort-Object Name -Descending
$keep = [System.Collections.Generic.HashSet[string]]::new()
$daily = $all | Select-Object -First $KeepDaily
foreach ($d in $daily) { $null = $keep.Add($d.Name) }
foreach ($d in $all) {
    # 매주 일요일 백업 보관
    $dt = [datetime]::ParseExact($d.Name, "yyyyMMdd-HHmmss", $null)
    if ($dt.DayOfWeek -eq [DayOfWeek]::Sunday) { $null = $keep.Add($d.Name) }
}
foreach ($d in $all) {
    if (-not $keep.Contains($d.Name)) {
        Write-Host "[backup]   purge $($d.Name)"
        Remove-Item $d.FullName -Recurse -Force
    }
}

Write-Host "[backup] done → $dst"
