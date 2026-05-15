# 밤샘 잡: translate(전체) -> fts 재빌드 -> embed 재실행
# 사용법:
#   .\scripts\overnight.ps1
# 또는 백그라운드:
#   Start-Process powershell -ArgumentList "-NoExit","-File","scripts\overnight.ps1"
#
# 모든 단계가 멱등: 캐시/state 가 있어 중간에 끊겨도 재실행 안전.
# 출력은 logs\overnight_*.log 에 저장.

$ErrorActionPreference = "Continue"   # 중간에 죽지 않도록
$env:PYTHONIOENCODING  = "utf-8"
$env:PYTHONPATH        = "."

$repo = "C:\kamoru\Workspace\git\flayAI"
Set-Location $repo

$logDir = Join-Path $repo "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "overnight_$ts.log"
$py  = Join-Path $repo ".venv\Scripts\python.exe"

function Step($name, [string[]]$cliArgs) {
    "" | Tee-Object -FilePath $log -Append
    "===== [$([DateTime]::Now.ToString('HH:mm:ss'))] $name =====" |
        Tee-Object -FilePath $log -Append
    & $py -m packages.indexer.cli @cliArgs 2>&1 | Tee-Object -FilePath $log -Append
    "----- exit=$LASTEXITCODE -----" | Tee-Object -FilePath $log -Append
}

"### overnight job started @ $ts ###" | Tee-Object -FilePath $log
"### log: $log ###"                    | Tee-Object -FilePath $log -Append

# 1) JP -> KO 전체 번역 (NLLB-200, CPU/GPU 자동). 캐시되어 재실행 안전.
Step "translate (full)" @("translate", "-v")

# 2) FTS5 재빌드 (title_ko, desc_ko 반영)
Step "fts rebuild"      @("fts", "-v")

# 3) bge-m3 임베딩 재실행 (한글 문서 포함된 새 템플릿으로 갱신).
#    Qdrant upsert 는 동일 ID 덮어쓰기 → 재실행 안전.
Step "embed (full)"     @("embed", "-v")

"### overnight job finished @ $([DateTime]::Now.ToString('yyyyMMdd_HHmmss')) ###" |
    Tee-Object -FilePath $log -Append
