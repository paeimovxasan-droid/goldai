"""PostgreSQL va Redis setup skripti"""
import sys
import io
import os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from dotenv import load_dotenv
load_dotenv()


def setup_postgres():
    try:
        import psycopg2
        from psycopg2 import sql
    except ImportError:
        print("[!!] psycopg2 o'rnatilmagan: pip install psycopg2-binary")
        return False

    # Superuser sifatida ulanish
    try:
        conn = psycopg2.connect(
            host="127.0.0.1", port=5432,
            user="postgres", password="",
            database="postgres"
        )
        conn.autocommit = True
        cur = conn.cursor()

        # User yaratish
        try:
            cur.execute("CREATE USER ultra WITH PASSWORD 'ultra_secure_2025';")
            print("[OK] User 'ultra' yaratildi")
        except Exception as e:
            if "already exists" in str(e):
                print("[OK] User 'ultra' allaqachon mavjud")
            else:
                print(f"[!!] User xato: {e}")

        # Database yaratish
        try:
            cur.execute("CREATE DATABASE goldai_ultra OWNER ultra;")
            print("[OK] Database 'goldai_ultra' yaratildi")
        except Exception as e:
            if "already exists" in str(e):
                print("[OK] Database allaqachon mavjud")
            else:
                print(f"[!!] DB xato: {e}")

        cur.execute("GRANT ALL PRIVILEGES ON DATABASE goldai_ultra TO ultra;")
        print("[OK] Huquqlar berildi")
        conn.close()
    except Exception as e:
        print(f"[!!] PostgreSQL superuser ulanish xatosi: {e}")
        print("     postgres foydalanuvchi paroli kerak bo'lishi mumkin.")
        return False

    # Schema yaratish (ultra foydalanuvchi sifatida)
    try:
        conn2 = psycopg2.connect(
            host="127.0.0.1", port=5432,
            user="ultra", password="ultra_secure_2025",
            database="goldai_ultra"
        )
        conn2.autocommit = True
        cur2 = conn2.cursor()

        with open("database/init.sql", "r", encoding="utf-8") as f:
            sql_content = f.read()

        cur2.execute(sql_content)
        print("[OK] Schema yaratildi (jadvallar va view'lar)")

        # Jadvallarni tekshirish
        cur2.execute("SELECT tablename FROM pg_tables WHERE schemaname='public';")
        tables = [row[0] for row in cur2.fetchall()]
        print(f"[OK] Jadvallar: {', '.join(tables)}")
        conn2.close()
        return True

    except Exception as e:
        print(f"[!!] Schema xatosi: {e}")
        return False


def setup_redis():
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)
        r.ping()
        r.set("goldai_ultra:status", "active")
        r.set("goldai_ultra:version", "1.0")
        print("[OK] Redis ishlayapti va ma'lumot yozildi")
        return True
    except Exception as e:
        print(f"[!!] Redis xato: {e}")
        return False


def test_connection():
    """DB ulanishini tekshirish"""
    db_url = os.getenv("DB_URL", "postgresql://ultra:ultra_secure_2025@localhost:5432/goldai_ultra")
    try:
        import psycopg2
        # URL ni parse qilish
        conn = psycopg2.connect(
            host="127.0.0.1", port=5432,
            user="ultra", password="ultra_secure_2025",
            database="goldai_ultra"
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM trades;")
        count = cur.fetchone()[0]
        print(f"[OK] DB ulanish muvaffaqiyatli | trades: {count} ta")
        conn.close()
        return True
    except Exception as e:
        print(f"[!!] DB ulanish xato: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("  GoldAI Ultra — Database Setup")
    print("=" * 50)

    print("\n[1] PostgreSQL:")
    pg_ok = setup_postgres()

    print("\n[2] Redis:")
    redis_ok = setup_redis()

    print("\n[3] Ulanish testi:")
    conn_ok = test_connection()

    print("\n" + "=" * 50)
    if pg_ok and redis_ok and conn_ok:
        print("[OK] Barcha ma'lumotlar bazalari tayyor!")
    else:
        print("[!!] Ba'zi muammolar bor. Yuqoridagi xatolarni tekshiring.")
    print("=" * 50)
