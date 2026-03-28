param(
    [Parameter(Mandatory = $true)]
    [string]$Url
)

$envPath = Join-Path $PSScriptRoot ".env"

if (-not (Test-Path $envPath)) {
    Write-Error ".env not found: $envPath"
    exit 1
}

if ($Url -notmatch '^https://') {
    Write-Error "MINI_APP_URL must start with https://"
    exit 1
}

$content = Get-Content $envPath -Raw

if ($content -match '(?m)^MINI_APP_URL=') {
    $updated = [regex]::Replace($content, '(?m)^MINI_APP_URL=.*$', "MINI_APP_URL=$Url")
} else {
    $updated = $content.TrimEnd("`r", "`n") + "`r`nMINI_APP_URL=$Url`r`n"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($envPath, $updated, $utf8NoBom)
Write-Host "Updated MINI_APP_URL in .env:"
Write-Host $Url
