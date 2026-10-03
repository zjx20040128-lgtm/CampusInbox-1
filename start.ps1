[CmdletBinding()]
param([string]$ListenHost='127.0.0.1',[int]$Port=8765,[switch]$NoBrowser,[switch]$CheckOnly)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'scripts\find-python.ps1')
$python = Resolve-CIPython
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$dotenv = Join-Path $PSScriptRoot '.env'
if (Test-Path -LiteralPath $dotenv) {
    foreach ($line in (Get-Content -LiteralPath $dotenv -Encoding UTF8)) {
        if ($line -match '^\s*(CI_MODEL_PROVIDER|CI_MODEL_BASE_URL|CI_MODEL|CI_MODEL_API_KEY|CI_ACCESS_TOKEN)\s*=\s*(.*?)\s*$') {
            [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2].Trim('"').Trim("'"),'Process')
        }
    }
}
if ($CheckOnly) {
    Write-Output "Python: $python"
    & $python --version
    Write-Output "Project: $PSScriptRoot"
    exit $LASTEXITCODE
}
$params = @((Join-Path $PSScriptRoot 'server.py'),'--host',$ListenHost,'--port',"$Port")
if (-not $NoBrowser) { $params += '--open-browser' }
& $python @params
exit $LASTEXITCODE
