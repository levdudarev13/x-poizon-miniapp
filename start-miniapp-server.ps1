$python = Get-Command python -ErrorAction SilentlyContinue

if (-not $python) {
    Write-Error "python not found in PATH"
    exit 1
}

Set-Location $PSScriptRoot
python miniapp_server.py
