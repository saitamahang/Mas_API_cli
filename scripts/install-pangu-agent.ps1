param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Wheel,

    [string]$Adapter = "codeagent",

    [string[]]$AdapterPackage = @(),

    [string[]]$PluginPackage = @(),

    [switch]$SkipConfig,

    [switch]$SkipDoctor,

    [switch]$NoForceSkill
)

$ErrorActionPreference = "Stop"

python -m pip install --upgrade $Wheel

foreach ($Package in $PluginPackage) {
    python -m pip install --upgrade $Package
}

foreach ($Package in $AdapterPackage) {
    python -m pip install --upgrade $Package
}

$InitArgs = @("init", "--install-skill", "--adapter", $Adapter)

if ($NoForceSkill) {
    $InitArgs += "--no-force-skill"
} else {
    $InitArgs += "--force-skill"
}

if ($SkipConfig) {
    $InitArgs += "--skip-config"
}

if ($SkipDoctor) {
    $InitArgs += "--skip-doctor"
}

$Command = Get-Command pangu-agent -ErrorAction SilentlyContinue
if ($Command) {
    & pangu-agent @InitArgs
} else {
    python -m pangu.agent_main @InitArgs
}
