param([switch]$Browser)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')
. (Join-Path $PSScriptRoot 'find-python.ps1')
$python = Resolve-CIPython
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
& $python -B -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($Browser) {
    $runtimeNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node'
    $node = Join-Path $runtimeNode 'bin\node.exe'
    if (-not (Test-Path -LiteralPath $node)) { $node = (Get-Command node -ErrorAction Stop).Source }
    $modules = Join-Path $runtimeNode 'node_modules'
    if (Test-Path -LiteralPath $modules) { $env:NODE_PATH = $modules }
    $env:CI_PYTHON=$python
    & $node scripts\browser-check.cjs
    exit $LASTEXITCODE
}
