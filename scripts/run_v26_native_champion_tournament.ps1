# Native V26 research tournament, never a live gameplay tool.
# Examples:
#   ./scripts/run_v26_native_champion_tournament.ps1 -DbPath 'data/torn-fren-stock-history-latest.db' -V19 'data/all_item_v19/master.json' -V20 'data/weak_item_v20/master.json' -V21 'data/all_item_v21/full_master.json' -Scope smoke -MaxStarts 12
#   ./scripts/run_v26_native_champion_tournament.ps1 ... -Scope all -MaxStarts 12 -Workers 8
#   ./scripts/run_v26_native_champion_tournament.ps1 ... -Scope all -MaxStarts 80 -Workers 8 -Output 'data/frozen_champion_v26/v26_80starts.json'
param(
 [Parameter(Mandatory=$true)][string]$DbPath,
 [Parameter(Mandatory=$true)][string]$V19,
 [Parameter(Mandatory=$true)][string]$V20,
 [Parameter(Mandatory=$true)][string]$V21,
 [ValidateSet('smoke','all')][string]$Scope='smoke',
 [ValidateRange(1,10000)][int]$MaxStarts=12,
 [ValidateRange(1,32)][int]$Workers=2,
 [string]$Output=''
)
$ErrorActionPreference='Stop'
foreach($p in @($DbPath,$V19,$V20,$V21)) {
 if(-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Missing input: $p" }
}
if (-not $Output) {
 $Output="data/frozen_champion_v26/${Scope}_${MaxStarts}starts.json"
}
$dir=Split-Path -Parent $Output
if($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$argv=@('-u','-m','services.frozen_champion_shadow_v24',
 '--db',$DbPath,
 '--v19',$V19,'--v20',$V20,'--v21',$V21,
 '--cutoff','1791241486',
 '--expected-db-sha256','d1e9fa488b987d06234643174236bf1c1f72bec607cf476b7f2dd39adf7eb583',
 '--max-starts',"$MaxStarts",'--workers',"$Workers",
 '--min-qty','30','--grace-seconds','10',
 '--v20-replan-seconds','300',
 '--output',$Output,'--resume')
if($Scope -eq 'smoke') {
 $argv+=@('--only','arg:Tear Gas','--only','can:Fire Hydrant','--only','chi:Katana')
}
Write-Host "V26 RESEARCH ONLY. Does not modify Torn, Discord, VM or production routes."
Write-Host "Input database SHA will be checked before execution."
& python @argv
if($LASTEXITCODE -ne 0) { throw "Native replay exited with code $LASTEXITCODE" }
Write-Host "Native research JSON: $Output"
