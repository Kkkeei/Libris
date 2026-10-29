@echo off
cd /d "%~dp0"
py -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name Libris --collect-all qrcode --collect-all PIL --collect-all customtkinter app.py
echo Executavel gerado em dist\Libris\Libris.exe
pause
