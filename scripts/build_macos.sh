#!/bin/sh
set -eu

python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --clean MMToolkit.spec

echo "Built: dist/MM Toolkit.app"
