param(
    [ValidateSet('serve', 'stop', 'reload-api', 'status')]
    [string]$Action = 'serve',
    [string]$Config = $env:TALK_RUNTIME_CONFIG,
    [switch]$Apply,
    [switch]$Foreground
)
$ErrorActionPreference = 'Stop'
if (-not $Config) {
    throw '请通过 -Config 指定仓库外运行清单，或设置 TALK_RUNTIME_CONFIG。详见 docs/guides/TALK_RUNTIME.md。'
}
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw '缺少项目 .venv Python，请先按部署指南安装依赖。'
}
$runtimeArgs = @('-B', '-X', 'utf8', '-m', 'scripts.talk_runtime', $Action, '--config', $Config)
if ($Apply) { $runtimeArgs += '--apply' }
if ($Action -eq 'serve' -and $Apply -and -not $Foreground) { $runtimeArgs += '--detach' }
Push-Location -LiteralPath $PSScriptRoot
try { & $python @runtimeArgs; $runtimeExitCode = $LASTEXITCODE }
finally { Pop-Location }
exit $runtimeExitCode
