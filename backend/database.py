from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings
from backend.models import Base, User

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_schema()


def _migrate_schema() -> None:
    db = SessionLocal()
    try:
        inspector = __import__("sqlalchemy").inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("users")]

        if "password_hash" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
        if "google_id" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN google_id VARCHAR(255)"))
        if "github_id" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN github_id VARCHAR(255)"))
        if "avatar_url" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(1024)"))
        if "telegram_bot_token" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN telegram_bot_token VARCHAR(255)"))
        if "wallet_address" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN wallet_address VARCHAR(255)"))
        if "auth_method" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN auth_method VARCHAR(20) NOT NULL DEFAULT 'password'"))
        if "email_verified" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"))

        if "email" in columns:
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)"))
        if "google_id" in columns:
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_users_google_id ON users(google_id)"))
        if "github_id" in columns:
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_users_github_id ON users(github_id)"))
        if "wallet_address" in columns:
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_users_wallet_address ON users(wallet_address)"))

        existing = db.query(User).filter(User.id == 1).first()
        if existing and not existing.password_hash and not existing.google_id and not existing.wallet_address:
            existing.auth_method = "password"
            from backend.config import settings as cfg
            import bcrypt
            existing.password_hash = bcrypt.hashpw(
                cfg.auth_password.encode(), bcrypt.gensalt()
            ).decode()
            db.commit()

        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
