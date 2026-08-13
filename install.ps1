[CmdletBinding(SupportsShouldProcess = $true, DefaultParameterSetName = 'Install')]
param(
    [Parameter(ParameterSetName = 'Install')]
    [string[]]$Skill,

    [Parameter(ParameterSetName = 'Install')]
    [switch]$All,

    [Parameter(ParameterSetName = 'Install')]
    [switch]$Update,

    [Parameter(Mandatory = $true, ParameterSetName = 'List')]
    [switch]$List,

    [Parameter(Mandatory = $true, ParameterSetName = 'Uninstall')]
    [switch]$Uninstall,

    [Parameter(ParameterSetName = 'Uninstall')]
    [string[]]$UninstallSkill,

    [string]$Destination
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$RepositoryId = 'zhangifexim-bit/harmonyos-agent-skills'
$MarkerName = '.harmonyos-agent-skills-install.json'
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ManifestPath = Join-Path $ScriptRoot 'skills-manifest.json'

function Resolve-SkillsDestination {
    param([string]$Requested)

    if ($Requested) {
        $candidate = [System.IO.Path]::GetFullPath($Requested)
    }
    elseif ($env:CODEX_HOME) {
        $candidate = [System.IO.Path]::GetFullPath((Join-Path $env:CODEX_HOME 'skills'))
    }
    else {
        $candidate = [System.IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('UserProfile')) '.codex\skills'))
    }

    $root = [System.IO.Path]::GetPathRoot($candidate)
    if (-not $candidate -or $candidate -eq $root) {
        throw 'Destination must be a dedicated skills directory, not a filesystem root.'
    }
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        throw 'Destination points to a file.'
    }
    return $candidate
}

function Get-DirectoryHash {
    param([Parameter(Mandatory = $true)][string]$Path)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $builder = New-Object System.Text.StringBuilder
        $files = Get-ChildItem -LiteralPath $Path -Recurse -File | Where-Object { $_.Name -ne $MarkerName } | Sort-Object FullName
        foreach ($file in $files) {
            $relative = $file.FullName.Substring($Path.Length).TrimStart('\', '/').Replace('\', '/')
            $fileHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
            [void]$builder.Append($relative).Append(':').Append($fileHash).Append("`n")
        }
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($builder.ToString())
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Read-InstallMarker {
    param([Parameter(Mandatory = $true)][string]$SkillPath)

    $markerPath = Join-Path $SkillPath $MarkerName
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        return $null
    }
    $marker = Get-Content -Raw -Encoding UTF8 -LiteralPath $markerPath | ConvertFrom-Json
    if ($marker.repository -ne $RepositoryId -or $marker.skill -ne (Split-Path -Leaf $SkillPath)) {
        return $null
    }
    return $marker
}

function Assert-UnmodifiedInstall {
    param([Parameter(Mandatory = $true)][string]$SkillPath)

    $marker = Read-InstallMarker -SkillPath $SkillPath
    if ($null -eq $marker) {
        throw "Cannot prove that '$SkillPath' belongs to this installer."
    }
    $currentHash = Get-DirectoryHash -Path $SkillPath
    if ($currentHash -ne $marker.installed_hash) {
        throw "Installed skill '$SkillPath' has local modifications; refusing destructive action."
    }
    return $marker
}

function Get-SelectedSkills {
    param($Manifest, [string[]]$Names, [bool]$SelectAll)

    $known = @($Manifest.skills | ForEach-Object { $_.name })
    if ($SelectAll) {
        return $known
    }
    if (-not $Names -or $Names.Count -eq 0) {
        return $known
    }
    foreach ($name in $Names) {
        if ($known -notcontains $name) {
            throw "Unknown skill '$name'. Valid skills: $($known -join ', ')."
        }
    }
    return @($Names | Select-Object -Unique)
}

function Install-SkillSafely {
    param([string]$Name, [string]$SkillsDestination, [bool]$AllowUpdate, $Manifest)

    $source = Join-Path (Join-Path $ScriptRoot 'skills') $Name
    $target = Join-Path $SkillsDestination $Name
    $exists = Test-Path -LiteralPath $target
    if ($exists -and -not $AllowUpdate) {
        throw "Target '$target' already exists. Nothing was overwritten."
    }
    if ($exists) {
        [void](Assert-UnmodifiedInstall -SkillPath $target)
    }
    if (-not $PSCmdlet.ShouldProcess($target, $(if ($exists) { 'Update skill' } else { 'Install skill' }))) {
        return
    }

    if (-not (Test-Path -LiteralPath $SkillsDestination)) {
        [void](New-Item -ItemType Directory -Path $SkillsDestination)
    }
    $staging = Join-Path $SkillsDestination ('.installing-' + $Name + '-' + [Guid]::NewGuid().ToString('N'))
    $backup = $null
    try {
        Copy-Item -Recurse -LiteralPath $source -Destination $staging
        $installedHash = Get-DirectoryHash -Path $staging
        $marker = [ordered]@{
            schema_version = '1.0'
            repository = $RepositoryId
            repository_version = $Manifest.repository_version
            skill = $Name
            installed_hash = $installedHash
        }
        $marker | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $staging $MarkerName)
        if ($exists) {
            $backup = $target + '.backup-' + [Guid]::NewGuid().ToString('N')
            Move-Item -LiteralPath $target -Destination $backup
        }
        Move-Item -LiteralPath $staging -Destination $target
        if ($backup) {
            Remove-Item -Recurse -LiteralPath $backup
        }
        Write-Output "Installed $Name -> $target"
    }
    catch {
        if (Test-Path -LiteralPath $staging) {
            Remove-Item -Recurse -LiteralPath $staging
        }
        if ($backup -and (Test-Path -LiteralPath $backup) -and -not (Test-Path -LiteralPath $target)) {
            Move-Item -LiteralPath $backup -Destination $target
        }
        throw
    }
}

$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $ManifestPath | ConvertFrom-Json
$skillsDestination = Resolve-SkillsDestination -Requested $Destination

if ($PSCmdlet.ParameterSetName -eq 'List') {
    foreach ($entry in $manifest.skills) {
        $dependencies = if ($entry.dependencies.Count -eq 0) { 'none' } else { $entry.dependencies -join ', ' }
        Write-Output "$($entry.name) (dependencies: $dependencies)"
    }
    return
}

if ($PSCmdlet.ParameterSetName -eq 'Uninstall') {
    $names = Get-SelectedSkills -Manifest $manifest -Names $UninstallSkill -SelectAll ($null -eq $UninstallSkill -or $UninstallSkill.Count -eq 0)
    foreach ($name in $names) {
        $target = Join-Path $skillsDestination $name
        if (-not (Test-Path -LiteralPath $target -PathType Container)) {
            throw "Skill '$name' is not installed at '$target'."
        }
        [void](Assert-UnmodifiedInstall -SkillPath $target)
        if ($PSCmdlet.ShouldProcess($target, 'Uninstall verified skill')) {
            Remove-Item -Recurse -LiteralPath $target
            Write-Output "Uninstalled $name"
        }
    }
    return
}

$selected = Get-SelectedSkills -Manifest $manifest -Names $Skill -SelectAll $All.IsPresent
foreach ($name in $selected) {
    Install-SkillSafely -Name $name -SkillsDestination $skillsDestination -AllowUpdate $Update.IsPresent -Manifest $manifest
}
