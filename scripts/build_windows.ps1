$ErrorActionPreference = "Stop"

py -m pip install -r requirements.txt
py -m PyInstaller --noconfirm --clean MediaToolsForRecordLabels.spec

Write-Host "Built: dist/Media Tools for Record Labels/Media Tools for Record Labels.exe"
