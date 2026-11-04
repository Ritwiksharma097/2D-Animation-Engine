@echo off
rem Starts the workbench server and opens the hub page (links to review, sandbox, demos, editor, specs).
rem First run: python -m pip install -r requirements.txt
cd /d "%~dp0"
start "" cmd /c "timeout /t 3 /nobreak >nul & start "" http://localhost:8000/workbench/hub.html"
python workbench\serve.py
pause
