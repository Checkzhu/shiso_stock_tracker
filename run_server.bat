@echo off
cd /d "%~dp0"
"C:\Users\14222\AppData\Local\Programs\Python\Python312\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
