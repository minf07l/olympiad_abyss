import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, select, insert, update

# Загружаем переменные окружения
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sqlite_path = os.path.join(BASE_DIR, "instance", "app.db")
sqlite_url = f"sqlite:///{sqlite_path}"

pg_url = os.environ.get("DATABASE_URL")
if pg_url and pg_url.startswith("postgres://"):
    pg_url = pg_url.replace("postgres://", "postgresql://", 1)
if not pg_url:
    raise RuntimeError("DATABASE_URL не найден! Укажи его в .env")
if "sslmode" not in pg_url:
    pg_url += "?sslmode=require"

# Подключения
eng_sqlite = create_engine(sqlite_url)
eng_pg = create_engine(pg_url)

meta_sqlite = MetaData()
meta_pg = MetaData()
meta_sqlite.reflect(bind=eng_sqlite)
meta_pg.reflect(bind=eng_pg)

tables_to_copy = ["user", "message", "poll", "vote"]

with eng_sqlite.connect() as conn_sqlite, eng_pg.connect() as conn_pg:
    for table_name in tables_to_copy:
        if table_name not in meta_sqlite.tables or table_name not in meta_pg.tables:
            print(f"❌ Таблица {table_name} не найдена в одной из баз, пропускаем.")
            continue

        table_sqlite = Table(table_name, meta_sqlite, autoload_with=eng_sqlite)
        table_pg = Table(table_name, meta_pg, autoload_with=eng_pg)

        sqlite_rows = conn_sqlite.execute(select(table_sqlite)).mappings().all()
        if not sqlite_rows:
            print(f"ℹ️ {table_name} пуста в SQLite, пропускаем.")
            continue

        pg_rows = {r["id"]: r for r in conn_pg.execute(select(table_pg)).mappings().all()}

        new_count = 0
        updated_count = 0

        for row in sqlite_rows:
            if row["id"] not in pg_rows:
                conn_pg.execute(insert(table_pg).values(**row))
                new_count += 1
            else:
                # Проверка на изменения
                if dict(row) != dict(pg_rows[row["id"]]):
                    conn_pg.execute(update(table_pg).where(table_pg.c.id == row["id"]).values(**row))
                    updated_count += 1

        print(f"✅ {table_name}: добавлено {new_count}, обновлено {updated_count}")

print("🎉 Миграция завершена!")
