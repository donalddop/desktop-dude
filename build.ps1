# Builds dist\DesktopDude (PyInstaller), publish\DesktopDude-standalone.zip and publish\DesktopDude-setup.exe.
# Needs uv; the installer step needs Inno Setup 6 (winget install JRSoftware.InnoSetup).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

uv run --with pyinstaller pyinstaller --noconfirm --clean --windowed --name DesktopDude `
    --icon assets\app.ico `
    --hidden-import pycaw.pycaw --hidden-import pycaw.utils --collect-submodules comtypes `
    desktop_dude.py
if ($LASTEXITCODE) { throw "pyinstaller failed" }

New-Item -ItemType Directory -Force publish | Out-Null
Copy-Item README.md, LICENSE dist\DesktopDude\
Compress-Archive -Force dist\DesktopDude publish\DesktopDude-standalone.zip

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" }
if (Test-Path $iscc) { & $iscc /Q Installer\DesktopDude.iss } else { Write-Warning "Inno Setup not found: skipped the installer" }
Get-ChildItem publish
