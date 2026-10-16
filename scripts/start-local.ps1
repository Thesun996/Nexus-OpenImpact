[CmdletBinding()]
param(
    [string]$Python,
    [ValidateSet('deepseek', 'rule')][string]$Provider,
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Check,
    [switch]$SmokeTest,
    [switch]$PromptKey
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Python) {
    foreach ($candidate in @('.local/python-env/Scripts/python.exe', '.venv/Scripts/python.exe')) {
        $candidatePath = Join-Path $projectRoot $candidate
        if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
            $Python = $candidatePath
            break
        }
    }
    if (-not $Python) { $Python = (Get-Command python.exe -ErrorAction Stop).Source }
}

[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$launchArguments = @('-u', (Join-Path $PSScriptRoot 'run_local.py'), '--api-port', "$ApiPort", '--frontend-port', "$FrontendPort")
if ($Provider) { $launchArguments += @('--provider', $Provider) }
if ($Check) { $launchArguments += '--check' }
if ($SmokeTest) { $launchArguments += '--smoke-test' }
if ($PromptKey) { $launchArguments += '--prompt-key' }
& $Python @launchArguments
exit $LASTEXITCODE
