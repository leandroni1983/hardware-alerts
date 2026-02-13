Set-StrictMode -Version Latest
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot
if (-not (Test-Path archive)) { New-Item -ItemType Directory -Path archive | Out-Null }
git status --porcelain
git checkout -b chore/cleanup
$files = @('tmp_test_cpu.py','tmp_test_amd.py')
foreach ($f in $files) {
    if (Test-Path $f) { git mv $f archive/ } else { Write-Output "Missing $f" }
}
if (Test-Path tmp_db) { git mv tmp_db archive/ } else { Write-Output 'No tmp_db' }
Get-ChildItem scripts -Filter 'debug_*.py' -File -ErrorAction SilentlyContinue | ForEach-Object { git mv $_.FullName archive/ }
Get-ChildItem scripts -Filter 'inspect_*.py' -File -ErrorAction SilentlyContinue | ForEach-Object { git mv $_.FullName archive/ }
git add -A
$commitResult = git commit -m "chore: archive temporary and debug scripts" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Output $commitResult
} else {
    Write-Output "Commit created."
}
Write-Output "Archive cleanup script finished."
