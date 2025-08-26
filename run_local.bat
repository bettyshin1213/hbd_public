@echo off
setlocal enabledelayedexpansion

REM ====== 프로젝트 루트로 이동 ======
cd /d %~dp0

REM ====== Python 3.11 확인 ======
where python3.11 >nul 2>nul
if errorlevel 1 (
    echo ❌ python3.11 이 설치되어 있지 않습니다.
    echo 👉 https://www.python.org/downloads/release/python-3110/ 또는 Windows용 pyenv 설치를 확인하세요.
    pause
    exit /b 1
)

REM ====== 가상환경 생성 ======
if not exist ".venv" (
    echo 📦 가상환경(.venv) 생성 중...
    python3.11 -m venv .venv
)

REM ====== 가상환경 활성화 ======
call .venv\Scripts\activate.bat

REM ====== pip 업그레이드 & 패키지 설치 ======
echo ⬆️ pip 업그레이드 및 requirements 설치...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

REM ====== DB 초기화 ======
echo 🗄️ DB 초기화 실행...
python init_db.py

REM ====== Flask 앱 실행 ======
echo 🚀 Flask 앱 실행 중... http://127.0.0.1:5001
python app.py

endlocal