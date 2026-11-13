param(
    [switch]$Apply,
    [string]$Repository = (Join-Path $env:USERPROFILE 'Desktop\torn-fren')
)
$ErrorActionPreference = 'Stop'
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
if (!(Test-Path -LiteralPath (Join-Path $Repository '.git'))) {
    throw "Local Torn-FREN Git checkout not found: $Repository"
}

# Package exactly the reviewed GitHub main commit; never package uncommitted files.
& git -C $Repository fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch the latest reviewed main branch.' }
$commit = (& git -C $Repository rev-parse origin/main).Trim()
if ($LASTEXITCODE -ne 0 -or !$commit) { throw 'Could not resolve origin/main.' }
$files = @(
    'web/first_release_assets/hotlist.html',
    'web/first_release_assets/hotlist.js',
    'web/first_release_assets/abroad-roster.json',
    'deploy/scripts/relocate_hotlist.py'
)
foreach ($file in $files) {
    & git -C $Repository cat-file -e "${commit}:$file"
    if ($LASTEXITCODE -ne 0) {
        throw "Hot List has not been merged into main or is incomplete: $file"
    }
}
$installer = & git -C $Repository show "${commit}:deploy/scripts/relocate_hotlist.py"
if ($LASTEXITCODE -ne 0 -or !$installer) { throw 'Could not retrieve the pinned installer.' }

$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$archive = Join-Path $env:TEMP "torn-fren-hotlist-route-$stamp.zip"
$remote = "/tmp/torn-fren-hotlist-route-$stamp.zip"
$report = Join-Path $env:USERPROFILE "Desktop\torn-fren-hotlist-route-$stamp.json"

try {
    & git -C $Repository archive --format=zip "--output=$archive" $commit -- @files
    if ($LASTEXITCODE -ne 0) { throw 'Could not package Hot List release files.' }
    & scp -i $key $archive "ubuntu@150.136.108.146:$remote"
    if ($LASTEXITCODE -ne 0) { throw 'Archive upload failed; the web server was not modified.' }

    $mode = if ($Apply) { '--apply' } else { '' }
    $inputScript = ($installer -join "`n") + "`n"
    $output = $inputScript | & ssh -i $key ubuntu@150.136.108.146 "sudo -n python3 - --package $remote $mode"
    $exitCode = $LASTEXITCODE
    $output | Set-Content -LiteralPath $report -Encoding utf8
    $output | Out-Host
    Write-Host "Report: $report"
    if ($exitCode -ne 0) { throw 'Hot List check or deployment did not pass. Share the saved JSON report.' }
    $result = ($output -join "`n") | ConvertFrom-Json
    if ($Apply) {
        if ($result.status -notin @('HOTLIST_ROUTE_DEPLOYED','HOTLIST_ROUTE_ALREADY_INSTALLED')) {
            throw "Hot List was not deployed. Check report: $report"
        }
        Write-Host "Hot List published: https://tornfren.duckdns.org/experimental (Ctrl+F5 to refresh)."
    } else {
        if ($result.status -ne 'HOTLIST_ROUTE_PREFLIGHT_PASSED') {
            throw "Unexpected preflight result: $($result.status)"
        }
        Write-Host 'Route correction preflight passed. Run with -Apply to update /experimental.'
    }
}
finally {
    Remove-Item -LiteralPath $archive -ErrorAction SilentlyContinue
}
