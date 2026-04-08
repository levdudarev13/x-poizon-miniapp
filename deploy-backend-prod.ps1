param(
    [string]$Commit = "",
    [string[]]$Paths = @(),
    [string]$Server = "getsuga@213.171.26.232",
    [string]$DeployPath = "/home/getsuga/x-poizon-miniapp",
    [string]$MiniappService = "x-poizon-miniapp.service",
    [string]$BotService = "x-poizon-bot.service",
    [string]$HealthUrl = "http://127.0.0.1:8081/api/health"
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

function Quote-Bash {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return "'" + ($Value -replace "'", "'""'""'") + "'"
}

function Resolve-BackendPathsFromCommit {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetCommit
    )

    $changedPaths = & git diff-tree --no-commit-id --name-only -r $TargetCommit 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Could not resolve changed files for commit $TargetCommit.`n$($changedPaths -join "`n")"
    }

    $resolved = New-Object System.Collections.Generic.List[string]

    foreach ($rawPath in $changedPaths) {
        $path = [string]$rawPath
        $path = $path.Trim()
        if (-not $path) {
            continue
        }

        switch -Wildcard ($path) {
            "auth.py" { $null = $resolved.Add($path); continue }
            "config.py" { $null = $resolved.Add($path); continue }
            "database.py" { $null = $resolved.Add($path); continue }
            "handlers/*" { $null = $resolved.Add($path); continue }
            "main.py" { $null = $resolved.Add($path); continue }
            "miniapp_server.py" { $null = $resolved.Add($path); continue }
            "models.py" { $null = $resolved.Add($path); continue }
            "requirements.txt" { $null = $resolved.Add($path); continue }
            "services/*" { $null = $resolved.Add($path); continue }
            "utils/*" { $null = $resolved.Add($path); continue }
        }
    }

    return $resolved | Sort-Object -Unique
}

Require-Command git
Require-Command ssh

if (-not $Commit.Trim()) {
    $Commit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not resolve current HEAD commit."
    }
}

$resolvedPaths = @($Paths | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($resolvedPaths.Count -eq 0) {
    $resolvedPaths = @(Resolve-BackendPathsFromCommit -TargetCommit $Commit)
}

if ($resolvedPaths.Count -eq 0) {
    throw "No backend paths to deploy. Pass -Paths explicitly or use a backend commit."
}

Write-Host "Deploying backend commit:"
Write-Host $Commit
Write-Host ""
Write-Host "Backend paths:"
$resolvedPaths | ForEach-Object { Write-Host " - $_" }
Write-Host ""
Write-Host "Target server:"
Write-Host $Server
Write-Host ""

$remoteScript = @'
set -euo pipefail

deploy_path="$1"
commit="$2"
miniapp_service="$3"
bot_service="$4"
health_url="$5"
shift 5

if [ "$#" -eq 0 ]; then
  echo "No backend paths provided." >&2
  exit 2
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
short_commit="$(printf '%.7s' "$commit")"
backup_dir="${deploy_path}-backups/${timestamp}-${short_commit}"

mkdir -p "$backup_dir"
cd "$deploy_path"

git fetch origin main >/dev/null
git rev-parse --verify "${commit}^{commit}" >/dev/null

for path in "$@"; do
  if [ -e "$path" ]; then
    mkdir -p "$backup_dir/$(dirname "$path")"
    cp -R "$path" "$backup_dir/$path"
  fi
done

git checkout "$commit" -- "$@"

sudo systemctl restart "$miniapp_service" "$bot_service"
sleep 4

miniapp_status="$(systemctl is-active "$miniapp_service")"
bot_status="$(systemctl is-active "$bot_service")"
health_payload="$(curl -fsS "$health_url")"

echo "BACKUP_DIR=$backup_dir"
echo "DEPLOYED_COMMIT=$commit"
echo "MINIAPP_STATUS=$miniapp_status"
echo "BOT_STATUS=$bot_status"
echo "HEALTH=$health_payload"
'@

$remoteArguments = @(
    $DeployPath,
    $Commit,
    $MiniappService,
    $BotService,
    $HealthUrl
) + $resolvedPaths

$remoteCommand = "bash -s -- " + (($remoteArguments | ForEach-Object { Quote-Bash $_ }) -join " ")
$remoteOutput = $remoteScript | & ssh -T $Server $remoteCommand 2>&1
$remoteOutput | ForEach-Object { Write-Host $_ }

if ($LASTEXITCODE -ne 0) {
    throw "Backend deploy failed."
}
