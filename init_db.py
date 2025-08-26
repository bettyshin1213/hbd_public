import os
import time
from urllib.parse import parse_qs, urlparse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from app import app, db

try:
    from models import *
except Exception as e:
    print("models import warning:", e)
    
def _sqlite_db_path_from_uri(uri: str) -> str | None:
    # sqlite:///app.db 형태에서 파일 경로만 추출
    if not uri or not uri.startswith("sqlite:///"):
        return None
    return uri.replace("sqlite:///", "", 1)

def _sqlite_table_columns(table: str) -> list[str]:
    with db.engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info('{table}')")).mappings().all()
        return [r["name"] for r in rows]

def reset_sqlite_if_legacy_schema():
    """
    포트폴리오 모드 + SQLite에서 'message.author' 같은 유물 스키마가 있으면
    DB 파일을 삭제하고 깨끗이 재생성한다.
    """
    if db.engine.dialect.name != "sqlite":
        return
    if not PORTFOLIO_MODE:
        return

    try:
        cols = _sqlite_table_columns("message")
    except Exception:
        # message 테이블 자체가 없으면 패스
        return

    # ✅ 유물 스키마 패턴: author 컬럼 존재(특히 NOT NULL로 만들어졌던 과거)
    if "author" in cols:
        print("🧹 Detected legacy column 'author' in table 'message' → resetting SQLite DB (PORTFOLIO_MODE)")
        # 연결/세션 정리
        try:
            db.session.close()
        except Exception:
            pass
        try:
            db.engine.dispose()
        except Exception:
            pass

        db_path = _sqlite_db_path_from_uri(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
        if db_path and os.path.exists(db_path):
            os.remove(db_path)
            print(f"🗑  removed {db_path}")

        # 깨끗이 재생성
        create_tables()
        print("✅ Fresh DB recreated")
        
IS_POSTGRES = app.config.get("SQLALCHEMY_DATABASE_URI", "").startswith("postgresql")
PORTFOLIO_MODE = (os.getenv("PORTFOLIO_MODE", "false").lower() == "true")

def _extract_search_path_from_url(db_url: str) -> str | None:
    """
    DB URL 쿼리스트링의 options=-csearch_path%3Dschema 형식에서 schema 추출
    예) ...?options=-csearch_path%3Dhbd  -> 'hbd'
    """
    try:
        parsed = urlparse(db_url)
        qs = parse_qs(parsed.query or "")
        options = (qs.get("options", [""])[0] or "")
        # ' -csearch_path=hbd ' 같은 문자열에서 마지막 '=' 뒤를 스키마로 간주
        if "search_path" in options and "=" in options:
            return options.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

def _extract_search_path_from_engine_options() -> str | None:
    """
    app.config['SQLALCHEMY_ENGINE_OPTIONS']['connect_args']['options']
    에서 -csearch_path=hbd 형태를 파싱
    """
    try:
        eng = app.config.get("SQLALCHEMY_ENGINE_OPTIONS") or {}
        ca = (eng.get("connect_args") or {})
        options = ca.get("options") or ""
        if "search_path" in options and "=" in options:
            return options.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

def _get_target_schema() -> str | None:
    """
    우선순위:
    1) DB URL의 options
    2) ENGINE_OPTIONS의 options
    3) 없음(None) 이면 기본(Postgres의 경우 보통 'public')
    """
    db_url = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    return _extract_search_path_from_url(db_url) or _extract_search_path_from_engine_options()

def wait_for_db(max_wait=60, interval=2):
    """Postgres일 때 DB가 준비될 때까지 ping."""
    uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    print(f"🔌 DB URI = {uri}")
    if not IS_POSTGRES:
        print("ℹ️ SQLite/기타 드라이버: 연결 대기 생략")
        return

    elapsed = 0
    while True:
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ DB connection OK")
            return
        except OperationalError as e:
            elapsed += interval
            if elapsed >= max_wait:
                print("❌ DB not ready within timeout:", repr(e))
                raise
            print(f"⏳ Waiting for DB... ({elapsed}/{max_wait}s)")
            time.sleep(interval)

def ensure_schema_if_needed():
    """
    Postgres에서 search_path 대상 스키마가 존재하지 않으면 생성.
    그 후 해당 스키마로 세션 search_path 설정.
    """
    if not IS_POSTGRES:
        return

    target_schema = _get_target_schema()
    if not target_schema or target_schema == "public":
        # 기본 public이면 생략(일반적으로 이미 존재)
        return

    print(f"🏷  target schema = {target_schema}")
    with db.engine.connect() as conn:
        # 스키마 생성
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {target_schema}"))
        # 세션 search_path 설정 (create_all 시 해당 스키마에 테이블 생성)
        conn.execute(text(f"SET search_path TO {target_schema}"))
        conn.commit()
    print("✅ schema ensured & search_path set")

def create_tables():
    """SQLAlchemy 모델 기준 테이블 생성"""
    db.create_all()
    print("✅ DB tables created/ensured")

def seed_dummy_if_portfolio():
    """
    포트폴리오 모드에서 테이블이 비어 있으면 간단한 더미 데이터 삽입.
    (개인정보 없이 데모용으로만)
    """
    if not PORTFOLIO_MODE:
        return

    try:
        # 이미 데이터가 있으면 스킵
        has_message = db.session.query(Message.id).first()
        has_note = db.session.query(BirthdayNote.id).first()
    except Exception as e:
        print("⚠️ seed check failed:", e)
        return

    changed = False
    if not has_note:
        db.session.add(BirthdayNote(content="🎉 데모용 생일 메시지입니다!", updated_at=datetime.now()))
        changed = True
    if not has_message:
        db.session.add(Message(nickname="익명", text="첫 번째 방명록! (데모)", created_at=datetime.now()))
        changed = True

    if changed:
        db.session.commit()
        print("🌱 Seeded demo data (PORTFOLIO_MODE)")

if __name__ == "__main__":
    with app.app_context():
        wait_for_db()
        ensure_schema_if_needed()
        create_tables()
        reset_sqlite_if_legacy_schema()
        seed_dummy_if_portfolio()
        print("✅ init_db done.")