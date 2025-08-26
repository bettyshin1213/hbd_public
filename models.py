# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# 공통 타임스탬프
class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.now)

# 사용자(생일자 계정 식별/로그인)
class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "app_user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_birthday = db.Column(db.Boolean, nullable=False, default=False)  # 생일자면 True

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self) -> str:
        return f"<User {self.username} birthday={self.is_birthday}>"

# 익명 방명록
class Message(TimestampMixin, db.Model):
    __tablename__ = "message"

    id = db.Column(db.Integer, primary_key=True)
    nickname = db.Column(db.String(50), nullable=True)
    text = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(512), nullable=True)
    pin_hash = db.Column(db.String(255), nullable=True)
    like_count = db.Column(db.Integer, nullable=False, default=0)


# 생일자 전용 메시지(유튜브 아래 편집 영역)
class BirthdayNote(TimestampMixin, db.Model):
    __tablename__ = "birthday_note"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False, default="")

    def __repr__(self) -> str:
        return f"<BirthdayNote {self.id}>"

# 개발자 letter to birthday user
class PrivateLetter(db.Model):
    __tablename__ = "private_letter"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    image_url = db.Column(db.String(512), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.now)

db.Index("ix_message_created_at_desc", Message.created_at.desc())