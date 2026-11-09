@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -c "import django" >nul 2>&1
if errorlevel 1 (
  echo 未找到 Django，请先在此文件夹运行：python -m pip install -r requirements.txt
  pause
  exit /b 1
)
python manage.py migrate --noinput
if errorlevel 1 (
  echo 数据库初始化失败。
  pause
  exit /b 1
)
echo 服务启动后，在电脑浏览器打开 http://127.0.0.1:8765/
python manage.py runserver 0.0.0.0:8765 --noreload
if errorlevel 1 pause
