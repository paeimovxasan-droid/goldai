"""Optional PostgreSQL/Redis setup helper.

Trading does not depend on either service; the application uses an in-memory
history fallback when PostgreSQL is unavailable.  Connection details come
from .env instead of hard-coded passwords.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:
    from core.config import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _db_parts() -> dict:
    url = os.getenv("DB_URL", "postgresql://ultra:ultra_secure_2025@localhost:5432/goldai_ultra")
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 5432,
        "user": parsed.username or "ultra",
        "password": parsed.password or "",
        "database": (parsed.path or "/goldai_ultra").lstrip("/"),
    }


def setup_postgres() -> bool:
    try:
        import psycopg2
        from psycopg2 import sql
    except ImportError:
        print("[ -] psycopg2-binary o'rnatilmagan — PostgreSQL ixtiyoriy")
        return False

    parts = _db_parts()
    db_name = parts["database"]
    try:
        admin = dict(parts, database=os.getenv("PGADMIN_DATABASE", "postgres"))
        admin_user = os.getenv("PGADMIN_USER", "postgres")
        admin_password = os.getenv("PGADMIN_PASSWORD", "")
        conn = psycopg2.connect(host=admin["host"], port=admin["port"], user=admin_user,
                                password=admin_password, database=admin["database"])
        conn.autocommit = True
        with conn.cursor() as cur:
            role = parts["user"]
            password = parts["password"]
            if role != admin_user:
                cur.execute(sql.SQL("CREATE USER {} WITH PASSWORD %s").format(sql.Identifier(role)), (password,))
                print(f"[OK] User '{role}' yaratildi")
            cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(db_name), sql.Identifier(role)))
            print(f"[OK] Database '{db_name}' yaratildi")
        conn.close()
    except Exception as exc:
        message = str(exc).lower()
        if "already exists" not in message:
            print(f"[!!] PostgreSQL admin ulanishi: {exc}")
            print("     DB_URL/PGADMIN_* ni tekshiring; bu servis majburiy emas.")
            return False
        print("[OK] PostgreSQL user/database allaqachon mavjud")

    try:
        conn = psycopg2.connect(**parts)
        conn.autocommit = True
        with conn.cursor() as cur:
            schema_path = ROOT / "init.sql"
            cur.execute(schema_path.read_text(encoding="utf-8"))
        conn.close()
        print("[OK] Schema yaratildi")
        return True
    except Exception as exc:
        print(f"[!!] Schema xatosi: {exc}")
        return False


def setup_redis() -> bool:
    try:
        import redis
        parsed = urlparse(os.getenv("REDIS_URL", "redis://localhost:6379"))
        client = redis.Redis(host=parsed.hostname or "localhost", port=parsed.port or 6379,
                             password=parsed.password, decode_responses=True)
        client.ping()
        client.set("goldai_ultra:status", "active")
        print("[OK] Redis ishlayapti")
        return True
    except ImportError:
        print("[ -] redis paketi o'rnatilmagan — Redis ixtiyoriy")
    except Exception as exc:
        print(f"[ -] Redis ishlamadi: {exc}")
    return False


def test_connection() -> bool:
    try:
        import psycopg2
        parts = _db_parts()
        conn = psycopg2.connect(**parts)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM trades")
            count = cur.fetchone()[0]
        conn.close()
        print(f"[OK] DB ulanishi muvaffaqiyatli | trades: {count} ta")
        return True
    except Exception as exc:
        print(f"[ -] DB ulanishi yo'q: {exc}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("  GoldAI Ultra — Optional Database Setup")
    print("=" * 50)
    pg_ok = setup_postgres()
    redis_ok = setup_redis()
    conn_ok = test_connection()
    print("\n[OK] Trading DB bo'lmasa ham bot ishlaydi (memory mode).")
    raise SystemExit(0 if pg_ok and conn_ok else 1)
