param(
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [string]$BindAddress = '127.0.0.1',
    [ValidateSet('demo', 'live')][string]$Mode,
    [switch]$NoInstall
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    $venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv .venv
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv .venv
        } else {
            throw 'Python 3.11 or newer is required. Install Python and reopen PowerShell.'
        }
        if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
    }
    & $venvPython -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'"
    if ($LASTEXITCODE -ne 0) { throw 'The virtual environment requires Python 3.11 or newer.' }
    if (-not $NoInstall) {
        if (Test-Path -LiteralPath 'requirements.lock') {
            & $venvPython -m pip install -r requirements.lock
            if ($LASTEXITCODE -ne 0) { throw 'Installing locked dependencies failed.' }
            & $venvPython -m pip install --no-deps .
        } else {
            & $venvPython -m pip install .
        }
        if ($LASTEXITCODE -ne 0) { throw 'Installing ScamSERP failed.' }
    }
    if ($Mode) { $env:SCAMSERP_MODE = $Mode }
    Write-Host "ScamSERP: http://${BindAddress}:$Port (Ctrl+C stops the server)"
    & $venvPython -m scamserp.cli serve --host $BindAddress --port $Port
    if ($LASTEXITCODE -ne 0) { throw "ScamSERP exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
