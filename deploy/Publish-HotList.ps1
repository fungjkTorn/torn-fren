param(
    [switch]$Apply,
    [string]$Repository = (Join-Path $env:USERPROFILE 'Desktop\torn-fren')
)
$ErrorActionPreference = 'Stop'
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
if (!(Test-Path -LiteralPath (Join-Path $Repository '.git'))) { throw "Torn-FREN checkout missing: $Repository" }
& git -C $Repository fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch latest reviewed main.' }
$commit = (& git -C $Repository rev-parse origin/main).Trim()
if ($LASTEXITCODE -ne 0 -or !$commit) { throw 'Cannot pin reviewed commit.' }
$server = 'ubuntu@150.136.108.146'

function Invoke-HotListRelease {
    param(
        [string]$Revision,
        [string[]]$Names,
        [string]$InstallerFile,
        [string]$Label,
        [switch]$Publish
    )
    foreach ($name in $Names) {
        & git -C $Repository cat-file -e "${Revision}:$name"
        if ($LASTEXITCODE -ne 0) { throw "Reviewed release file not found: $name" }
    }
    $installer = & git -C $Repository show "${Revision}:$InstallerFile"
    if ($LASTEXITCODE -ne 0 -or !$installer) { throw "Installer unavailable: $InstallerFile" }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $archive = Join-Path $env:TEMP "torn-fren-$Label-$stamp.zip"
    $remote = "/tmp/torn-fren-$Label-$stamp.zip"
    $report = Join-Path $env:USERPROFILE "Desktop\torn-fren-$Label-$stamp.json"
    try {
        & git -C $Repository archive --format=zip "--output=$archive" $Revision -- @Names
        if ($LASTEXITCODE -ne 0) { throw 'Could not build reviewed release archive.' }
        & scp -i $key $archive "${server}:$remote"
        if ($LASTEXITCODE -ne 0) { throw 'Could not upload reviewed archive. No changes were made.' }
        $mode = if ($Publish) { '--apply' } else { '' }
        $source = ($installer -join "`n") + "`n"
        $result = $source | & ssh -i $key $server "sudo -n python3 - --package $remote $mode"
        $sshCode = $LASTEXITCODE
        $result | Set-Content -LiteralPath $report -Encoding utf8
        $result | Out-Host
        Write-Host "Report: $report"
        if ($sshCode -ne 0) { throw "Guarded $Label release stopped. Share the JSON report; do not retry blindly." }
        return ($result -join "`n") | ConvertFrom-Json
    }
    finally {
        Remove-Item -LiteralPath $archive -ErrorAction SilentlyContinue
    }
}

# The older Hot List was deployed to / before its /experimental route correction.
# Run that one-time migration from its immutable, already-reviewed commit only if needed.
$headers = @{ 'Cache-Control' = 'no-cache' }
$homepageHtml = (Invoke-WebRequest -UseBasicParsing -Uri 'https://tornfren.duckdns.org/' -Headers $headers).Content
$experimental = (Invoke-WebRequest -UseBasicParsing -Uri 'https://tornfren.duckdns.org/experimental' -Headers $headers).Content
$alreadyRouted = $homepageHtml.Contains('beta.js') -and $experimental.Contains('hotlist.js')
$needsMigration = $homepageHtml.Contains('hotlist.js') -and $experimental.Contains('beta.js')
if (!$alreadyRouted -and !$needsMigration) {
    throw 'Unexpected live routing. No changes were made; share the current site screenshots.'
}
if ($needsMigration) {
    Write-Host 'Installing reviewed /experimental route correction first.'
    $routeCommit = '1db892dcd81059adfd809f0c4c062ccd4513a330'
    $routeFiles = @(
        'web/first_release_assets/hotlist.html',
        'web/first_release_assets/hotlist.js',
        'web/first_release_assets/abroad-roster.json',
        'deploy/scripts/relocate_hotlist.py'
    )
    $route = Invoke-HotListRelease -Revision $routeCommit -Names $routeFiles -InstallerFile 'deploy/scripts/relocate_hotlist.py' -Label 'hotlist-route' -Publish:$Apply
    if ($Apply) {
        if ($route.status -notin @('HOTLIST_ROUTE_DEPLOYED','HOTLIST_ROUTE_ALREADY_INSTALLED')) {
            throw "Routing migration not verified: $($route.status)"
        }
    } else {
        Write-Host 'Route migration preflight complete. Run with -Apply to migrate and publish Nikeh Hot List.'
        return
    }
}
$uiFiles = @(
    'web/first_release_assets/hotlist.html',
    'web/first_release_assets/hotlist.js',
    'web/first_release_assets/hotlist-core.js',
    'web/first_release_assets/hotlist.css',
    'deploy/scripts/publish_hotlist_profitability.py'
)
$ui = Invoke-HotListRelease -Revision $commit -Names $uiFiles -InstallerFile 'deploy/scripts/publish_hotlist_profitability.py' -Label 'hotlist-nikeh' -Publish:$Apply
if ($Apply) {
    if ($ui.status -notin @('HOTLIST_NIKEH_DEPLOYED','HOTLIST_NIKEH_ALREADY_INSTALLED')) {
        throw "Hot List UI rollout not verified: $($ui.status)"
    }
    Write-Host 'Nikeh Hot List published: https://tornfren.duckdns.org/experimental (Ctrl+F5).'
} else {
    if ($ui.status -notin @('HOTLIST_NIKEH_PREFLIGHT_PASSED','HOTLIST_NIKEH_ALREADY_INSTALLED')) {
        throw "Hot List preflight not confirmed: $($ui.status)"
    }
    Write-Host 'Read-only preflight passed. Run -Apply to publish.'
}
