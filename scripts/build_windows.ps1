$ErrorActionPreference = "Stop"

py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean MMToolkit.spec

Write-Host "Built: dist/MM Toolkit/MM Toolkit.exe"
