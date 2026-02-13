Set-StrictMode -Version Latest
$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot
Write-Output "Removing __pycache__ directories..."
Get-ChildItem -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output "Removing $__".FullName
    Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Output "Removing .pyc files..."
Get-ChildItem -Recurse -Include '*.pyc' -File -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Output ("Removing " + $_.FullName)
    Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
}
Write-Output "Staging and committing cleanup changes..."
git add -A
$c = git commit -m 'chore: remove __pycache__ and .pyc artifacts' 2>&1
if ($LASTEXITCODE -ne 0) { Write-Output $c } else { Write-Output 'Committed cache cleanup' }
Write-Output "Done."
