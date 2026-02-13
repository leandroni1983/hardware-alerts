Set-StrictMode -Version Latest
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot
if (-not (Test-Path archive)) { New-Item -ItemType Directory -Path archive | Out-Null }
$patterns = @('tmp_test_cpu.py','tmp_test_amd.py','tmp_db')

foreach ($p in $patterns) {
    if (Test-Path $p) {
        $dest = Join-Path "archive" $p
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        Move-Item -Path $p -Destination $dest -Force
        Write-Output "Moved $p -> $dest"
    } else {
        Write-Output "Not present: $p"
    }
}

# Move debug_*.py and inspect_*.py from scripts/
Get-ChildItem scripts -Filter 'debug_*.py' -File -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = Join-Path 'scripts' $_.Name
    $dest = Join-Path 'archive' $rel
    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    Move-Item -Path $rel -Destination $dest -Force
    Write-Output "Moved $rel -> $dest"
}
Get-ChildItem scripts -Filter 'inspect_*.py' -File -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = Join-Path 'scripts' $_.Name
    $dest = Join-Path 'archive' $rel
    $destDir = Split-Path $dest -Parent
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    Move-Item -Path $rel -Destination $dest -Force
    Write-Output "Moved $rel -> $dest"
}

# Add moved files and commit
git add archive -A
$commitResult = git commit -m "chore: archive selected untracked temp/debug files" 2>&1
if ($LASTEXITCODE -ne 0) { Write-Output $commitResult } else { Write-Output "Commit created." }
Write-Output "Done."
