@echo off
cd /d "%~dp0"
py -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name Libris --collect-all qrcode --collect-all PIL --collect-all customtkinter --collect-all pdfplumber --collect-all openpyxl --collect-all xlrd --collect-all odf --collect-all docx app.py
echo Executavel gerado em dist\Libris\Libris.exe
pause
