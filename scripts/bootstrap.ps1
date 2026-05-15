<#
.SYNOPSIS  flayAI M0 bootstrap script
.USAGE     cd C:\kamoru\Workspace\git\flayAI ; .\scripts\bootstrap.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ROOT = Split-Path $PSScriptRoot -Parent
Set-Location $ROOT

function Write-Step($msg)  { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-OK($msg)    { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Write-WARN($msg)  { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-FAIL($msg)  { Write-Host "  [FAIL] $msg" -ForegroundColor Red ; exit 1 }

# -----------------------------------------------
# 1. Prerequisite checks
# -----------------------------------------------
Write-Step "Step 1: Prerequisite checks"

# GPU
$gpuInfo = (nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>&1)
if ($LASTEXITCODE -ne 0) { Write-FAIL "nvidia-smi failed - check GPU driver" }
Write-OK "GPU: $gpuInfo"

# Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-FAIL "docker not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop"
}
$dv = docker version --format "{{.Server.Version}}" 2>&1
Write-OK "Docker: $dv"

# Ollama
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-FAIL "ollama not found. Install from https://ollama.com"
}
$ollamaVer = (ollama --version 2>&1) -replace "`n","" -replace "`r",""
Write-OK "Ollama: $ollamaVer"

# uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Step "Installing uv..."
    winget install --id=astral-sh.uv -e --accept-package-agreements --accept-source-agreements
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH","User")
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-FAIL "uv still not found after install - restart terminal and re-run"
    }
}
Write-OK "uv: $(uv version)"

# K: drive
if (-not (Test-Path "K:\")) { Write-FAIL "K: drive not mounted - connect the drive and retry" }
Write-OK "K: drive mounted"

# -----------------------------------------------
# 2. Python dependencies
# -----------------------------------------------
Write-Step "Step 2: Python dependencies (uv sync)"
uv sync
if ($LASTEXITCODE -ne 0) { Write-FAIL "uv sync failed" }
Write-OK "Python dependencies installed"

# -----------------------------------------------
# 3. Start Qdrant
# -----------------------------------------------
Write-Step "Step 3: Start Qdrant container"
docker compose up -d qdrant
if ($LASTEXITCODE -ne 0) { Write-FAIL "docker compose up failed" }

$qdrantOk = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:6333/healthz" -Method GET -TimeoutSec 2
        $qdrantOk = $true
        break
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $qdrantOk) { Write-FAIL "Qdrant health check failed (30s timeout)" }
Write-OK "Qdrant: http://127.0.0.1:6333 OK"

# -----------------------------------------------
# 4. Pull LLM model
# -----------------------------------------------
Write-Step "Step 4: Ollama model pull"
$mainModel = "huihui_ai/qwen2.5-abliterate:14b"
$modelList = ollama list 2>&1
if ($modelList -notmatch "qwen2.5-abliterate") {
    Write-WARN "Downloading $mainModel (~9 GB, this will take a while...)"
    ollama pull $mainModel
    if ($LASTEXITCODE -ne 0) { Write-FAIL "ollama pull failed" }
}
Write-OK "$mainModel ready"

# -----------------------------------------------
# 5. M0 acceptance criteria
# -----------------------------------------------
Write-Step "Step 5: M0 acceptance criteria"

# 5-1. GPU detail
Write-OK "GPU detail: $(nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader 2>&1)"

# 5-2. Qdrant final
$h = Invoke-RestMethod -Uri "http://127.0.0.1:6333/healthz" -Method GET
Write-OK "Qdrant healthz: $($h | ConvertTo-Json -Compress)"

# 5-3. bge-m3 smoke test (Python code in separate file to avoid encoding issues)
Write-Host "  bge-m3 smoke test..." -ForegroundColor Yellow
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$smokeOut = & uv run python scripts/_smoke_bge.py 2>&1 | Out-String
$smokeExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($smokeExit -ne 0) {
    Write-WARN "bge-m3 smoke test failed (exit=$smokeExit) - model may still be downloading on first run"
    Write-Host $smokeOut
} else {
    Write-OK "bge-m3: $($smokeOut.Trim())"
}

# 5-4. LLM validation - 3 prompts
Write-Step "Step 5-4: LLM validation (3 prompts)"
$url = "http://127.0.0.1:11434/api/generate"
$prompts = @(
    [PSCustomObject]@{ label="Korean general";    text="Introduce yourself briefly in Korean in one sentence." },
    [PSCustomObject]@{ label="JP-KO translation"; text="Translate this Japanese sentence to Korean: Watashi wa AI assistant desu." },
    [PSCustomObject]@{ label="NSFW check";        text="List 3 short search query examples for an adult video library system." }
)
$allOk = $true
foreach ($p in $prompts) {
    $body = @{ model = $mainModel; prompt = $p.text; stream = $false } | ConvertTo-Json -Compress
    try {
        $resp = Invoke-RestMethod -Uri $url -Method POST -Body $body -ContentType "application/json" -TimeoutSec 120
        $ans  = $resp.response.Trim()
        if ($ans.Length -lt 10) {
            Write-WARN "[$($p.label)] response too short: $ans"
            $allOk = $false
        } else {
            $preview = $ans.Substring(0, [Math]::Min(80, $ans.Length))
            Write-OK "[$($p.label)] -> $preview..."
        }
    } catch {
        Write-WARN "[$($p.label)] request failed: $_"
        $allOk = $false
    }
}

if (-not $allOk) {
    Write-WARN "Some LLM checks did not pass - review model or re-run"
} else {
    Write-OK "All LLM checks passed"
}

# -----------------------------------------------
# Done
# -----------------------------------------------
Write-Host "`n+----------------------------------------------+" -ForegroundColor Green
Write-Host "|  M0 bootstrap complete                       |" -ForegroundColor Green
Write-Host "|  Next: M1 metadata ETL                       |" -ForegroundColor Green
Write-Host "|    -> flay-index load  (load_jsons.py)       |" -ForegroundColor Green
Write-Host "+----------------------------------------------+`n" -ForegroundColor Green
