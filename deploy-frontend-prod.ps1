param(
    [string]$RepoRoot = $PSScriptRoot,
    [switch]$SkipBuild,
    [switch]$SkipInspect
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Require-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command not found: $Name"
    }
}

Require-Command git
Require-Command npm
Require-Command npx

$resolvedRepoRoot = (Resolve-Path $RepoRoot).Path
$miniappRoot = Join-Path $resolvedRepoRoot "miniapp"

if (-not (Test-Path $miniappRoot)) {
    throw "miniapp directory not found: $miniappRoot"
}

Push-Location $resolvedRepoRoot
try {
    if (-not $SkipBuild) {
        Write-Host "Building frontend..."
        Push-Location $miniappRoot
        try {
            & npm run build
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend build failed."
            }
        } finally {
            Pop-Location
        }
    }

    Write-Host "Deploying frontend to Vercel production..."
    $deployOutput = & npx vercel deploy --prod --yes 2>&1
    $deployOutput | ForEach-Object { Write-Host $_ }

    if ($LASTEXITCODE -ne 0) {
        throw "Vercel production deploy failed."
    }

    $vercelUrls = [regex]::Matches(
        ($deployOutput -join "`n"),
        'https://[A-Za-z0-9.-]+\.vercel\.app'
    )

    if ($vercelUrls.Count -eq 0) {
        throw "Could not detect a Vercel deployment URL in the deploy output."
    }

    $deployUrl = $vercelUrls[$vercelUrls.Count - 1].Value
    Write-Host ""
    Write-Host "Frontend deploy is ready:"
    Write-Host $deployUrl

    if (-not $SkipInspect) {
        Write-Host ""
        Write-Host "Inspecting deployment aliases..."
        & npx vercel inspect $deployUrl
        if ($LASTEXITCODE -ne 0) {
            throw "Vercel inspect failed."
        }
    }
} finally {
    Pop-Location
}
