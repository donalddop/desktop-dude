@echo off
type %LOCALAPPDATA%\DesktopDude\desktop_dude.log | findstr /n . | more +0 > nul
powershell -NoProfile -Command "Get-Content $env:LOCALAPPDATA\DesktopDude\desktop_dude.log -Tail 3"
tasklist /fi "imagename eq DesktopDude.exe" /fo csv /nh
reg query HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\{3B6F0D2E-7C41-4A8B-9E15-2F6A8C4D1E97}_is1 /v DisplayVersion
