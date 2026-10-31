# Build PrintEasy-Setup.exe on a Windows PC.
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build_installer.ps1
# Needs Python 3.11+ (python.org) and Inno Setup 6 (https://jrsoftware.org/isinfo.php, or: winget install JRSoftware.InnoSetup)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

python -m pip install -r requirements.txt pyinstaller pillow
python packaging\make_icons.py
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist\PrintEasy) { Remove-Item dist\PrintEasy -Recurse -Force }
pyinstaller --noconfirm printeasy.spec

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup" }
& $iscc packaging\windows\printeasy.iss

# Optional: sign it so Windows SmartScreen doesn't warn people (needs a code-signing certificate)
if ($env:WIN_SIGN_CERT) {
  signtool sign /f $env:WIN_SIGN_CERT /p $env:WIN_SIGN_PASSWORD /tr http://timestamp.digicert.com /td sha256 /fd sha256 `
    dist\installers\PrintEasy-Setup-1.0.0-Windows.exe
}
Write-Host "Built dist\installers\PrintEasy-Setup-1.0.0-Windows.exe"
