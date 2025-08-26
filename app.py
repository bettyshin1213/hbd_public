from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, g,
    send_from_directory, jsonify
)
from datetime import datetime, timedelta
from models import BirthdayNote, Message, PrivateLetter, db
from dotenv import load_dotenv
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import os, re, shutil, time, hashlib
import json, threading

load_dotenv()

app = Flask(
    __name__,
    static_folder="static_example",
    static_url_path="/static_example"
)

# === 모드/환경 변수 ===
IS_PROD = (os.getenv("FLASK_ENV", "").lower() == "production")
PORTFOLIO_MODE = (os.getenv("PORTFOLIO_MODE", "false").lower() == "true")

# === 기본 설정 ===
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///app.db")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "please_change_me")
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = timedelta(days=365)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if IS_PROD:
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["PREFERRED_URL_SCHEME"] = "https"

# 엔진 옵션: Postgres일 때만 search_path/pool 옵션 적용
if DATABASE_URL.startswith("postgresql"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "connect_args": {"options": "-csearch_path=hbd"},  # DB URL의 search_path와 통일 권장
        "pool_size": 10,
        "max_overflow": 2,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
else:
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {}

# LB 뒤에서 원 IP/프로토콜 보존
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)  # type: ignore

db.init_app(app)

# ====== 정적 URL 헬퍼 ======
_static_digest_cache = {}  # {(filename, mtime): "abcdef1234"}

def _digest_of_static(filename: str) -> str:
    path = os.path.join(app.static_folder, filename)
    try:
        mtime = os.path.getmtime(path)
        key = (filename, mtime)
        if key in _static_digest_cache:
            return _static_digest_cache[key]
        with open(path, "rb") as f:
            h = hashlib.md5(f.read()).hexdigest()[:10]
        _static_digest_cache[key] = h
        return h
    except Exception:
        return "0"

def static_v(filename: str) -> str:
    v = _digest_of_static(filename)
    return url_for("static", filename=filename, v=v)

@app.context_processor
def inject_static_helper():
    return {"static_v": static_v}

# ====== 사진 저장소 (로컬 디스크) ======
BASE_DIR = app.root_path
SRC_PHOTOS_DIR  = os.path.join(BASE_DIR, "static_example", "photos")       # 시드(읽기 전용)
EDIT_PHOTOS_DIR = os.path.join(BASE_DIR, "media_example", "photos_edit")   # 편집/업로드본
ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp"}

def allowed(fname: str) -> bool:
    return "." in fname and fname.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def ensure_edit_dir_seed():
    """
    편집용 폴더가 '없을 때만' 원본(/static_example/photos)을 통째로 복제해서 시드한다.
    그 이후엔 media만 사용(비어있을 수도 있음).
    """
    if os.path.exists(EDIT_PHOTOS_DIR):
        return
    os.makedirs(os.path.dirname(EDIT_PHOTOS_DIR), exist_ok=True)
    if os.path.isdir(SRC_PHOTOS_DIR):
        shutil.copytree(SRC_PHOTOS_DIR, EDIT_PHOTOS_DIR)
    else:
        os.makedirs(EDIT_PHOTOS_DIR, exist_ok=True)

# ====== 권한 ======
def require_birthday(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_birthday"):
            flash("접근 권한이 없습니다. 생일자만 이용 가능합니다.", "error")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.before_request
def inject_flag():
    g.is_birthday = bool(session.get("is_birthday"))

# ====== 공통 응답 ======
def is_json_request() -> bool:
    if request.is_json:
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept

def json_or_redirect(ok: bool, msg: str, status: int = 200, redirect_ep="index", **extra):
    if is_json_request():
        payload = {"ok": ok, "message": msg}
        if extra:
            payload.update(extra)
        return jsonify(payload), status
    else:
        flash(msg, "success" if ok else "error")
        return redirect(url_for(redirect_ep))

def verify_pin_or_birthday(msg: Message, pin: str | None, is_birthday: bool):
    if is_birthday:
        return True, None
    if not pin or not pin.isdigit() or len(pin) != 4:
        return False, "비밀번호(숫자 4자리)를 입력하세요."
    if not msg.pin_hash:
        return False, "이 메시지는 생성 시 비밀번호가 없어, 작성자 수정/삭제가 불가합니다. 생일자만 가능합니다."
    if not check_password_hash(msg.pin_hash, pin):
        return False, "비밀번호가 일치하지 않습니다."
    return True, None

# ====== 크롬 디버그 파일 요청 무시 ======
@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def ignore_chrome_devtools():
    return '', 204

# ====== 로그인/로그아웃 ======
@app.get("/login")
def login():
    return render_template("login.html")

@app.post("/login")
def do_login():
    password = request.form.get("password", "")
    if password == os.getenv("BIRTHDAY_PASS"):
        session["is_birthday"] = True
        flash("로그인되었습니다.", "success")
        nxt = request.args.get("next") or url_for("index")
        return redirect(nxt)
    flash("비밀번호가 올바르지 않습니다.", "error")
    return redirect(url_for("login"))

@app.post("/logout")
def logout():
    session.clear()
    flash("로그아웃되었습니다.", "success")
    return redirect(url_for("index"))

# === letter 전용 사진 헬퍼 ===
LETTER_PHOTOS_DIR = os.path.join(app.static_folder, "letter")

def list_letter_photos():
    if not os.path.isdir(LETTER_PHOTOS_DIR):
        return []
    files = [f for f in os.listdir(LETTER_PHOTOS_DIR) if allowed(f)]
    files.sort(key=lambda x: x.lower())
    photos = []
    for f in files:
        try:
            mtime = int(os.path.getmtime(os.path.join(LETTER_PHOTOS_DIR, f)))
        except Exception:
            mtime = 0
        photos.append({
            "url": url_for("static", filename=f"letter/{f}") + (f"?v={mtime}" if mtime else ""),
            "name": f
        })
    return photos

def list_media_photos():
    ensure_edit_dir_seed()
    files = [f for f in os.listdir(EDIT_PHOTOS_DIR) if allowed(f)]
    files.sort(key=lambda x: x.lower())
    photos = []
    for f in files:
        try:
            mtime = int(os.path.getmtime(os.path.join(EDIT_PHOTOS_DIR, f)))
        except Exception:
            mtime = 0
        photos.append({
            "url": url_for("media_file", filename=f) + (f"?v={mtime}" if mtime else ""),
            "name": f
        })
    return photos

# ====== 메인 ======
@app.route("/")
def index():
    photos = list_media_photos()
    note = BirthdayNote.query.first()
    messages = Message.query.order_by(Message.created_at.desc()).all()
    session_liked = set(session.get("liked_msgs", []))
    return render_template(
        "index.html",
        youtube_id=os.getenv("YOUTUBE_ID", "YG5qy6baxCA"),
        birthday_note=note,
        anon_messages=messages,
        session_liked=session_liked,
        birthday_username=os.getenv("BIRTHDAY_USERNAME", "birthday-user"),
        current_year=datetime.now().year,
        photos=photos,
    )

# ====== 로컬 편집본 서빙 ======
@app.route("/media_example/photos/<path:filename>")
def media_file(filename):
    ensure_edit_dir_seed()
    return send_from_directory(EDIT_PHOTOS_DIR, filename, conditional=True)

# ====== 생일자 메시지 저장 ======
@app.post("/owner-note", endpoint="edit_birthday_note")
@require_birthday
def edit_birthday_note():

    if PORTFOLIO_MODE:
        return json_or_redirect(False, "포트폴리오 모드에서는 저장이 비활성화되어 있습니다.", status=403)

    content = (request.form.get("content") or "")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    content = content.lstrip("\uFEFF")
    content = re.sub(r"^\s*\n+", "", content).strip(" \t\n\r\u00A0")
    if not content:
        return json_or_redirect(False, "메시지를 입력하세요.")

    note = BirthdayNote.query.first()
    if note:
        note.content = content
        note.updated_at = datetime.now()
    else:
        note = BirthdayNote(content=content, updated_at=datetime.now())
        db.session.add(note)

    db.session.commit()
    return json_or_redirect(True, "생일자 메시지가 저장되었습니다.")

# ====== 사진 업로드/삭제/초기화 (로컬) ======
@app.post("/photos/upload")
@require_birthday
def upload_photo():
    if PORTFOLIO_MODE:
        return json_or_redirect(False, "포트폴리오 모드에서는 업로드가 비활성화되어 있습니다.", status=403)

    ensure_edit_dir_seed()
    f = request.files.get("file")
    if not f or f.filename == "":
        return json_or_redirect(False, "파일을 선택하세요.")
    if not allowed(f.filename):
        return json_or_redirect(False, "허용되지 않는 확장자입니다.")

    name = secure_filename(f.filename)
    target = os.path.join(EDIT_PHOTOS_DIR, name)
    if os.path.exists(target):
        root, ext = os.path.splitext(name)
        name = f"{root}_{int(time.time())}{ext.lower()}"
        target = os.path.join(EDIT_PHOTOS_DIR, name)

    try:
        f.save(target)
        return json_or_redirect(True, "업로드 완료!")
    except Exception as e:
        print("⚠️ upload save error:", e)
        return json_or_redirect(False, "업로드 중 오류가 발생했습니다.", status=500)

@app.post("/photos/delete/<path:filename>")
@require_birthday
def delete_photo(filename):
    if PORTFOLIO_MODE:
        return json_or_redirect(False, "포트폴리오 모드에서는 삭제가 비활성화되어 있습니다.", status=403)

    ensure_edit_dir_seed()
    target = os.path.join(EDIT_PHOTOS_DIR, filename)
    if os.path.isfile(target):
        try:
            os.remove(target)
            return json_or_redirect(True, "삭제 완료!")
        except Exception as e:
            print("⚠️ delete error:", e)
            return json_or_redirect(False, "삭제 중 오류가 발생했습니다.", status=500)
    else:
        return json_or_redirect(False, "파일이 존재하지 않습니다.", status=404)

def _clear_dir(path: str):
    """path 내부의 파일/디렉터리만 삭제 (path 자체는 유지)."""
    if not os.path.isdir(path):
        return
    for root, dirs, files in os.walk(path, topdown=False):
        for fname in files:
            fp = os.path.join(root, fname)
            try:
                os.chmod(fp, 0o666)
            except Exception:
                pass
            try:
                os.remove(fp)
            except Exception:
                pass
        for dname in dirs:
            dp = os.path.join(root, dname)
            try:
                os.chmod(dp, 0o777)
            except Exception:
                pass
            try:
                os.rmdir(dp)
            except Exception:
                pass

def _copy_dir_contents(src: str, dst: str):
    """src의 내용물을 dst 최상위로 복사 (dst는 비어있다고 가정하지 않음)."""
    if not os.path.isdir(src):
        return
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

@app.post("/photos/reset")
@require_birthday
def reset_photos():
    if PORTFOLIO_MODE:
        return json_or_redirect(False, "포트폴리오 모드에서는 초기화가 비활성화되어 있습니다.", status=403)

    # 1) 편집 폴더 보장
    os.makedirs(EDIT_PHOTOS_DIR, exist_ok=True)

    # 2) 내용물만 싹 비우기(디렉터리 자체는 삭제하지 않음)
    try:
        _clear_dir(EDIT_PHOTOS_DIR)
    except Exception as e:
        print("⚠️ clear_dir error:", e)
        return json_or_redirect(False, "초기화 중 오류가 발생했습니다.", status=500)

    # 3) 원본(static/photos)로 다시 채우기
    try:
        if os.path.isdir(SRC_PHOTOS_DIR):
            _copy_dir_contents(SRC_PHOTOS_DIR, EDIT_PHOTOS_DIR)
    except Exception as e:
        print("⚠️ copy_dir_contents error:", e)
        return json_or_redirect(False, "원본 복구 중 오류가 발생했습니다.", status=500)

    return json_or_redirect(True, "초기 상태(원본)로 복구했습니다.")

# ====== 방명록 ======
@app.post("/guestbook/add")
def add_anon_message():
    nickname = (request.form.get("nickname") or "").strip() or "익명"
    text = (request.form.get("text") or "").strip()
    pin = (request.form.get("pin") or "").strip()

    if not text:
        return json_or_redirect(False, "메시지를 입력하세요.")

    pin_hash = None
    if pin:
        if not (pin.isdigit() and len(pin) == 4):
            return json_or_redirect(False, "비밀번호는 숫자 4자리로 입력하세요.")
        pin_hash = generate_password_hash(pin)

    msg = Message(nickname=nickname, text=text, created_at=datetime.now(), pin_hash=pin_hash)
    db.session.add(msg)
    db.session.commit()
    notify_new_message(msg)

    extra = {
        "message_id": msg.id,
        "nickname": msg.nickname,
        "text": msg.text,
        "created_at": msg.created_at.isoformat(),
        "like_count": getattr(msg, "like_count", 0),
    }
    return json_or_redirect(True, "방명록이 등록되었습니다.", extra=extra)

@app.post("/guestbook/<int:message_id>/verify")
def verify_message_pin(message_id):
    msg = Message.query.get_or_404(message_id)
    pin = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        pin = (data.get("pin") or "").strip()
    else:
        pin = (request.form.get("pin") or "").strip()

    ok, err = verify_pin_or_birthday(msg, pin, g.is_birthday)
    if not ok:
        return json_or_redirect(False, err, status=400)

    return json_or_redirect(True, "인증 성공")

@app.post("/guestbook/<int:message_id>/update")
def edit_anon_message_update(message_id):
    msg = Message.query.get_or_404(message_id)

    if request.is_json:
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        nickname = (data.get("nickname") or "").strip()
        pin = (data.get("pin") or "").strip()
    else:
        text = (request.form.get("text") or "").strip()
        nickname = (request.form.get("nickname") or "").strip()
        pin = (request.form.get("pin") or "").strip()

    if not text:
        return json_or_redirect(False, "메시지를 입력하세요.", status=400)

    ok, err = verify_pin_or_birthday(msg, pin, g.is_birthday)
    if not ok:
        return json_or_redirect(False, err, status=400)

    if nickname:
        msg.nickname = nickname
    msg.text = text
    db.session.commit()
    notify_update_message(msg)

    return json_or_redirect(True, "수정되었습니다.")

@app.post("/guestbook/<int:message_id>/delete")
def delete_anon_message(message_id):
    msg = Message.query.get_or_404(message_id)
    if request.is_json:
        data = request.get_json(silent=True) or {}
        pin = (data.get("pin") or "").strip()
    else:
        pin = (request.form.get("pin") or "").strip()

    ok, err = verify_pin_or_birthday(msg, pin, g.is_birthday)
    if not ok:
        return json_or_redirect(False, err, status=400)

    db.session.delete(msg)
    db.session.commit()
    notify_delete_message(message_id, nick=msg.nickname or "(익명)")
    return json_or_redirect(True, "삭제되었습니다.", extra={"message_id": message_id})

# ====== 좋아요(세션당 1회) & 언좋아요 ======
def _get_session_liked_set():
    return set(session.get("liked_msgs", []))

def _save_session_liked_set(s):
    session["liked_msgs"] = list(s)

@app.post("/messages/<int:message_id>/like")
def like_message(message_id):
    msg = Message.query.get_or_404(message_id)
    liked_set = _get_session_liked_set()
    if message_id in liked_set:
        return jsonify(ok=True, liked=True, count=msg.like_count or 0)
    if msg.like_count is None:
        msg.like_count = 0
    msg.like_count += 1
    db.session.commit()
    liked_set.add(message_id)
    _save_session_liked_set(liked_set)
    return jsonify(ok=True, liked=True, count=msg.like_count or 0)

@app.post("/messages/<int:message_id>/unlike")
def unlike_message(message_id):
    msg = Message.query.get_or_404(message_id)
    liked_set = _get_session_liked_set()
    if message_id not in liked_set:
        return jsonify(ok=True, liked=False, count=msg.like_count or 0)
    if msg.like_count is None:
        msg.like_count = 0
    msg.like_count = max(0, msg.like_count - 1)
    db.session.commit()
    liked_set.remove(message_id)
    _save_session_liked_set(liked_set)
    return jsonify(ok=True, liked=False, count=msg.like_count or 0)

# ====== 기타 ======
@app.get("/letter")
@require_birthday
def letter_view():
    photos = list_letter_photos()
    return render_template("letter.html", photos=photos)

@app.after_request
def add_static_cache_headers(resp):
    try:
        p = request.path or ""
    except Exception:
        return resp
    static_prefix = (app.static_url_path or "/static_example") + "/"
    if p.startswith(static_prefix):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp

@app.teardown_appcontext
def shutdown_session(exception=None):
    try:
        db.session.remove()
    except Exception:
        pass

def _notify_slack(text: str):
    # 포트폴리오/로컬 데모에서는 슬랙 전송 차단
    if PORTFOLIO_MODE:
        return
    url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not url:
        return
    try:
        import urllib.request
        data = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).read()
    except Exception as e:
        print("⚠️ slack notify error:", e)

def notify_new_message(m):
    """방명록 등록 시 Slack으로 비동기 알림"""
    made = m.created_at.strftime("%Y-%m-%d %H:%M") if getattr(m, "created_at", None) else ""
    nick = m.nickname or "익명"
    text = (m.text or "").strip()
    text_short = text if len(text) <= 300 else text[:300] + "…"

    slack_text = (
        "📝 *새 방명록*\n"
        f"- 작성자: {nick}\n"
        f"- 시간: {made}\n"
        f"- 내용:\n{text_short}"
    )

    def worker():
        _notify_slack(slack_text)

    threading.Thread(target=worker, daemon=True).start()

def notify_update_message(m):
    """방명록 수정 시 Slack 알림"""
    made = datetime.now().strftime("%Y-%m-%d %H:%M")
    nick = m.nickname or "익명"
    text = (m.text or "").strip()
    text_short = text if len(text) <= 300 else text[:300] + "…"

    slack_text = (
        "✏️ *방명록 수정*\n"
        f"- 작성자: {nick}\n"
        f"- 시간: {made}\n"
        f"- 수정 후 내용:\n{text_short}"
    )
    threading.Thread(target=lambda: _notify_slack(slack_text), daemon=True).start()

def notify_delete_message(m_id, nick="(알 수 없음)"):
    """방명록 삭제 시 Slack 알림"""
    made = datetime.now().strftime("%Y-%m-%d %H:%M")
    slack_text = (
        "🗑 *방명록 삭제*\n"
        f"- ID: {m_id}\n"
        f"- 시간: {made}\n"
        f"- 작성자: {nick}"
    )
    threading.Thread(target=lambda: _notify_slack(slack_text), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False, use_reloader=True)