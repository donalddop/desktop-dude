# Builds dist\DesktopDude (PyInstaller), publish\DesktopDude-standalone.zip and publish\DesktopDude-setup.exe.
# Needs uv; the installer step needs Inno Setup 6 (winget install JRSoftware.InnoSetup).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

uv run --with pyinstaller pyinstaller --noconfirm --clean --windowed --name DesktopDude `
    --icon assets\app.ico `
    --hidden-import truststore --hidden-import pycaw.pycaw --hidden-import pycaw.utils --collect-submodules comtypes `
    --hidden-import soundcard --collect-data soundcard --collect-data faster_whisper --collect-binaries ctranslate2 `
    --add-data "assets\fonts;assets\fonts" `
    desktop_dude.py
if ($LASTEXITCODE) { throw "pyinstaller failed" }

# PySide6 brings an older OpenSSL and PyInstaller lets it win over Python's own, which breaks
# Python's _ssl (no https: no update checks, no weather). Python's newer copy serves Qt fine too.
$pyDlls = Join-Path (uv run python -c "import sys; print(sys.base_prefix)") "DLLs"
Copy-Item "$pyDlls\libssl-3-x64.dll", "$pyDlls\libcrypto-3-x64.dll" dist\DesktopDude\_internal\ -Force
$st = Start-Process dist\DesktopDude\DesktopDude.exe -ArgumentList "--selftest" -Wait -PassThru
if ($st.ExitCode -ne 0) { throw "selftest failed: the exe can't do https (see %LOCALAPPDATA%\DesktopDude\desktop_dude.log)" }

New-Item -ItemType Directory -Force publish | Out-Null
Copy-Item README.md, LICENSE dist\DesktopDude\
Compress-Archive -Force dist\DesktopDude publish\DesktopDude-standalone.zip

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" }
$ver = (Select-String appdir.py -Pattern 'VERSION = "(.+)"').Matches[0].Groups[1].Value
if (Test-Path $iscc) { & $iscc /Q "/DAppVersion=$ver" Installer\DesktopDude.iss } else { Write-Warning "Inno Setup not found: skipped the installer" }
Write-Host "Built version $ver"
Get-ChildItem publish
