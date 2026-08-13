[CmdletBinding()]
param(
    [Parameter()]
    [string]$DevEcoPath,

    [Parameter()]
    [string]$ProjectPath = (Get-Location).Path,

    [Parameter()]
    [switch]$Json
)

$implementation = Join-Path $PSScriptRoot '..\skills\harmonyos-build-doctor\scripts\check-deveco-env.ps1'
if (-not (Test-Path -LiteralPath $implementation -PathType Leaf)) {
    throw "Bundled implementation not found: $implementation"
}

& $implementation @PSBoundParameters
