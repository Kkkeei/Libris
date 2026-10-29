#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
sudo apt install -y python3-tk python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name Libris --collect-all qrcode --collect-all PIL --collect-all customtkinter --collect-all pdfplumber --collect-all openpyxl --collect-all xlrd --collect-all odf --collect-all docx app.py
echo "Executável gerado em: $PWD/dist/Libris"
