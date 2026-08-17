#!/bin/sh
set -eu

python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --clean MediaToolsForRecordLabels.spec

echo "Built: dist/Media Tools for Record Labels.app"
