@echo off
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Chua co Python virtual environment. Xem README.md.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo Chua build frontend. Chay: cd frontend ^& npm.cmd ci ^& npm.cmd run build
  pause
  exit /b 1
)
echo English AI Adventure: http://127.0.0.1:8000
echo Hoc sinh: http://127.0.0.1:8000/#/play
echo Ma giao vien: mo file backend\data\teacher-access.txt sau khi server khoi dong.
echo Nhan Ctrl+C de dung server.
backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
pause
