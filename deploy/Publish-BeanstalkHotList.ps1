param(
    [switch]$Apply,
    [string]$Repository = (Join-Path $env:USERPROFILE 'Desktop\torn-fren')
)
$ErrorActionPreference = 'Stop'
$sshKey = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $sshKey)) { throw "Missing approved VM SSH key: $sshKey" }
if (!(Test-Path -LiteralPath (Join-Path $Repository '.git'))) { throw "Missing Torn-FREN checkout: $Repository" }

& git -C $Repository fetch origin main
if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed. No deployment attempted.' }
$revision = (& git -C $Repository rev-parse origin/main).Trim()
if ($LASTEXITCODE -ne 0 -or !$revision) { throw 'Could not pin reviewed main commit.' }

$files = @(
    'web/beanstalk_hot_list.py',
    'deploy/scripts/publish_beanstalk_hot_list.py'
)
foreach ($file in $files) {
    & git -C $Repository cat-file -e ($revision + ':' + $file)
    if ($LASTEXITCODE -ne 0) { throw "Reviewed file missing: $file" }
}
$installerLines = & git -C $Repository show ($revision + ':deploy/scripts/publish_beanstalk_hot_list.py')
if ($LASTEXITCODE -ne 0 -or !$installerLines) { throw 'Could not load reviewed endpoint installer.' }
$installer = ($installerLines -join [Environment]::NewLine) + [Environment]::NewLine

$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$archive = Join-Path $env:TEMP "torn-fren-beanstalk-hotlist-$stamp.zip"
$remote = "/tmp/torn-fren-beanstalk-hotlist-$stamp.zip"
$report = Join-Path $env:USERPROFILE "Desktop\torn-fren-beanstalk-hotlist-$stamp.json"
$hostTarget = 'ubuntu@150.136.108.146'
try {
    & git -C $Repository archive --format=zip "--output=$archive" $revision -- @files
    if ($LASTEXITCODE -ne 0) { throw 'Archive creation failed. No VM changes made.' }
    & scp -i $sshKey $archive ($hostTarget + ':' + $remote)
    if ($LASTEXITCODE -ne 0) { throw 'Secure upload failed. No VM changes made.' }
    $mode = if ($Apply) { '--apply' } else { '' }
    $output = $installer | & ssh -i $sshKey $hostTarget "sudo -n python3 - --package $remote $mode"
    $exitCode = $LASTEXITCODE
    $output | Set-Content -LiteralPath $report -Encoding utf8
    $output | Out-Host
    Write-Host "Report: $report"
    if ($exitCode -ne 0) { throw "Guarded endpoint installation stopped. Share report; do not bypass safety checks." }
    $response = ($output -join [Environment]::NewLine) | ConvertFrom-Json
    if ($Apply) {
        if ($response.status -notin @('BEANSTALK_HOT_LIST_DEPLOYED','BEANSTALK_HOT_LIST_ALREADY_INSTALLED')) {
            throw "Unexpected deployment outcome: $($response.status)"
        }
        Write-Host 'Beanstalk seven-pick API LIVE: https://tornfren.duckdns.org/api/beanstalk-hot-list'
    } else {
        Write-Host 'Read-only preflight passed. Rerun with -Apply to publish the seven-pick endpoint.'
    }
}
finally {
    Remove-Item -LiteralPath $archive -ErrorAction SilentlyContinue
}
