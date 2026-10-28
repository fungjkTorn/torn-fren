param([string]$PackagePath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (!$PackagePath) {
    $picker = New-Object System.Windows.Forms.OpenFileDialog
    $picker.Title = 'Select TORN_FREN_FIRST_TEN_LIVE.zip'
    $picker.Filter = 'ZIP archives (*.zip)|*.zip'
    if ($picker.ShowDialog() -ne 'OK') { return }
    $PackagePath = $picker.FileName
}
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
$zip = [System.IO.Compression.ZipFile]::OpenRead($PackagePath)
$installer = Join-Path $env:TEMP ('torn-fren-install-' + [guid]::NewGuid().ToString('N') + '.py')
try {
    $entry = $zip.GetEntry('installer.py')
    if (!$entry -or !$zip.GetEntry('manifest.json')) {
        throw 'Select TORN_FREN_FIRST_TEN_LIVE.zip. This archive is not the live release package.'
    }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $installer, $true)
}
finally { $zip.Dispose() }
$remote = '/tmp/torn-fren-first-ten-' + [guid]::NewGuid().ToString('N') + '.zip'
$report = Join-Path $env:USERPROFILE 'Desktop\torn-fren-first-ten-deployment.json'
try {
    & scp -i $key $PackagePath "ubuntu@150.136.108.146:$remote"
    if ($LASTEXITCODE -ne 0) { throw 'Upload failed. No installer was started.' }
    $output = Get-Content -Raw -LiteralPath $installer |
        & ssh -i $key ubuntu@150.136.108.146 "sudo -n python3 - --package $remote"
    $exitCode = $LASTEXITCODE
    $output | Set-Content -Encoding utf8 -LiteralPath $report
    $output | Out-Host
    Write-Host "Deployment report: $report"
    if ($exitCode -ne 0) { throw 'Deployment stopped. Upload the report before retrying.' }
    $result = ($output -join "`n") | ConvertFrom-Json
    if ($result.status -ne 'FIRST_TEN_BETA_LIVE_INITIAL_CHECKS_PASSED') {
        throw 'Activation is not confirmed. Upload the deployment report.'
    }
    Write-Host 'Initial deployment checks passed: https://tornfren.duckdns.org/experimental'
    Write-Host 'Scheduled cadence and live accuracy still need observation.'
}
finally { Remove-Item -LiteralPath $installer -ErrorAction SilentlyContinue }
