param([string]$PackagePath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (!$PackagePath) {
    $picker = New-Object System.Windows.Forms.OpenFileDialog
    $picker.Title = 'Select TORN_FREN_UI_UPDATE.zip'
    $picker.Filter = 'ZIP archives (*.zip)|*.zip'
    if ($picker.ShowDialog() -ne 'OK') { return }
    $PackagePath = $picker.FileName
}
$key = Join-Path $env:USERPROFILE 'Desktop\.ssh\torn-fren.key'
if (!(Test-Path -LiteralPath $key)) { throw "SSH key missing: $key" }
$zip = [System.IO.Compression.ZipFile]::OpenRead($PackagePath)
$installer = Join-Path $env:TEMP ('torn-fren-ui-' + [guid]::NewGuid().ToString('N') + '.py')
try {
    $entry = $zip.GetEntry('installer.py')
    if (!$entry -or !$zip.GetEntry('manifest.json')) { throw 'Wrong archive. Select TORN_FREN_UI_UPDATE.zip.' }
    $reader = New-Object System.IO.StreamReader($zip.GetEntry('manifest.json').Open())
    try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    if ($manifest.ui_revision -ne 'compact-planner-v1') { throw 'Wrong UI update selected.' }
    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $installer, $true)
}
finally { $zip.Dispose() }
$remote = '/tmp/torn-fren-ui-' + [guid]::NewGuid().ToString('N') + '.zip'
$report = Join-Path $env:USERPROFILE 'Desktop\torn-fren-ui-update.json'
try {
    & scp -i $key $PackagePath "ubuntu@150.136.108.146:$remote"
    if ($LASTEXITCODE -ne 0) { throw 'Upload failed; no update started.' }
    $output = Get-Content -Raw -LiteralPath $installer |
        & ssh -i $key ubuntu@150.136.108.146 "sudo -n python3 - --package $remote"
    $exitCode = $LASTEXITCODE
    $output | Set-Content -Encoding utf8 -LiteralPath $report
    $output | Out-Host
    Write-Host "Update report: $report"
    if ($exitCode -ne 0) { throw 'UI update stopped. Send the report before retrying.' }
    $result = ($output -join "`n") | ConvertFrom-Json
    if ($result.status -notin @('UI_UPDATE_CHECKS_PASSED', 'UI_ALREADY_INSTALLED')) { throw 'UI update is not confirmed. Send the report.' }
    Write-Host 'UI update installed. Refresh the website with Ctrl+F5.'
}
finally { Remove-Item -LiteralPath $installer -ErrorAction SilentlyContinue }
