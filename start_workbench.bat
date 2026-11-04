@echo off
rem Starts the workbench server and opens the owner review page.
rem First run: python -m pip install -r requirements.txt
cd /d "%~dp0"
start "" cmd /c "timeout /t 3 /nobreak >nul & start "" http://localhost:8000/workbench/review.html"
python workbench\serve.py
pause
