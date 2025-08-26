#!/bin/bash
set -e

# ====== 프로젝트 루트로 이동 ======
# (스크립트 파일이 위치한 폴더 기준으로 cd)
cd "$(dirname "$0")"

# ====== Python 3.11 확인 ======
if ! command -v python3.11 &> /dev/null
then
    echo "❌ python3.11 이 설치되어 있지 않습니다."
    echo "👉 Homebrew 로 설치하세요: brew install python@3.11"
    exit 1
fi

# ====== 가상환경 생성 ======
if [ ! -d ".venv" ]; then
    echo "📦 가상환경(.venv) 생성 중..."
    python3.11 -m venv .venv
fi

# ====== 가상환경 활성화 ======
source .venv/bin/activate

# ====== pip 업그레이드 & 패키지 설치 ======
echo "⬆️ pip 업그레이드 및 requirements 설치..."
pip install --upgrade pip
pip install -r requirements.txt

# ====== DB 초기화 ======
echo "🗄️ DB 초기화 실행..."
python init_db.py

# ====== Flask 앱 실행 ======
echo "🚀 Flask 앱 실행 중... http://127.0.0.1:5001"
python app.py