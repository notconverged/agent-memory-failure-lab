$ErrorActionPreference = "Stop"
$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$pluginPath = Resolve-Path (Join-Path $PSScriptRoot "..")
python -m pip install -e $repositoryRoot
codex plugin install --dev $pluginPath
