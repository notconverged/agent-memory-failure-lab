param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("create", "verify", "export-lock", "recreate")]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [ValidateSet("basic-memory", "mem0", "letta", "graphiti")]
    [string]$System,

    [switch]$ConfirmRecreate
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvironmentNames = @{
    "basic-memory" = "amlab-basic-memory"
    "mem0" = "amlab-mem0"
    "letta" = "amlab-letta"
    "graphiti" = "amlab-graphiti"
}
$EnvironmentName = $EnvironmentNames[$System]
$Definition = Join-Path $ProjectRoot "environments\competitors\$System.yml"
$LockFile = Join-Path $ProjectRoot "environments\locks\$System-windows.txt"

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "conda is not available on PATH"
}

switch ($Action) {
    "create" {
        conda env create -f $Definition
    }
    "verify" {
        conda run -n agent-memory-failure-lab python (Join-Path $ProjectRoot "scripts\run_competitor_trial.py") verify-env --system $System
    }
    "export-lock" {
        $Freeze = conda run -n $EnvironmentName python -m pip freeze
        $Freeze | Set-Content -LiteralPath $LockFile -Encoding utf8
        Write-Output "Wrote $LockFile"
    }
    "recreate" {
        if (-not $ConfirmRecreate) {
            throw "Recreate deletes only '$EnvironmentName'. Repeat with -ConfirmRecreate."
        }
        conda env remove -n $EnvironmentName -y
        conda env create -f $Definition
    }
}
