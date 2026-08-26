# ─────────────────────────────────────────────────────────────────────────
# start_studio.ps1 — Lance LangGraph Studio pour déboguer l'agent V3
#
# Usage :
#   .\start_studio.ps1
#   .\start_studio.ps1 -Port 2025
# ─────────────────────────────────────────────────────────────────────────

param(
    [int]$Port = 2024
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "=== LangGraph Studio — Agent d'Apprentissage V3 ===" -ForegroundColor Cyan

# ── 1. Vérifier / démarrer Ollama local ──────────────────────────────────
Write-Host "`n[1/3] Vérification d'Ollama local..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3
    $models = $response.models.name -join ", "
    Write-Host "  Ollama tourne. Modèles : $models" -ForegroundColor Green
} catch {
    Write-Host "  Ollama ne répond pas. Démarrage..." -ForegroundColor Yellow
    $ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $ollamaExe) {
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 4
        Write-Host "  Ollama démarré." -ForegroundColor Green
    } else {
        Write-Host "  ERREUR : Ollama introuvable à $ollamaExe" -ForegroundColor Red
        exit 1
    }
}

# ── 2. Vérifier le venv ──────────────────────────────────────────────────
Write-Host "`n[2/3] Vérification de l'environnement Python..." -ForegroundColor Yellow
$venvPython = Join-Path $ProjectRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "  ERREUR : venv introuvable. Créez-le avec : python -m venv venv" -ForegroundColor Red
    exit 1
}

# Vérifier langgraph-cli
$cliCheck = & $venvPython -c "import langgraph_cli; print('ok')" 2>&1
if ($cliCheck -ne "ok") {
    Write-Host "  langgraph-cli absent. Installation..." -ForegroundColor Yellow
    & $venvPython -m pip install "langgraph-cli[inmem]"
}
Write-Host "  Environnement prêt." -ForegroundColor Green

# ── 3. Lancer LangGraph Studio ───────────────────────────────────────────
Write-Host "`n[3/3] Lancement de LangGraph Studio sur le port $Port..." -ForegroundColor Yellow
Write-Host "  Le graphe utilise le LLM LOCAL (qwen2.5-coder:3b) — aucun quota cloud." -ForegroundColor DarkGray
Write-Host "  Appuyez sur Ctrl+C pour arrêter.`n" -ForegroundColor DarkGray

$env:PYTHONPATH = $ProjectRoot
& (Join-Path $ProjectRoot "venv\Scripts\langgraph.exe") dev --port $Port
