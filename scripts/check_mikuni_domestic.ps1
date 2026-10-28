# Run official replay diagnostic from a permitted domestic Windows host.
# Requires Docker Desktop; no VPN/proxy or raw video ingestion.
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
docker build -q -f (Join-Path $repoRoot "docker/mikuni-domestic-check/Dockerfile") -t boatlab-mikuni-domestic-check $repoRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker run --rm --pull=never --read-only --tmpfs " /tmp:rw,nosuid,size=512m".Trim() --tmpfs "/home/pwuser:rw,nosuid,size=256m" --shm-size=512m --memory=1536m --cpus=2 --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=256 boatlab-mikuni-domestic-check @args
exit $LASTEXITCODE
