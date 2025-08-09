import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, select, insert

# Загружаем переменные окружения (.env)
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sqlite_path = os.path.join(BASE_DIR, "instance", "app.db")

# URL для SQLite (локальная база)
sqlite_url = f"sqlite:///{sqlite_path}"

# URL для PostgreSQL (Render)
pg_url = os.environ.get("DATABASE_URL")
if pg_url and pg_url.startswith("postgres://"):
    pg_url = pg_url.replace("postgres://", "postgresql://", 1)

if not pg_url:
    raise RuntimeError("DATABASE_URL не найден! Убедись, что он есть в .env или переменных окружения.")

# Создаём движки
eng_sqlite = create_engine(sqlite_url)
eng_pg = create_engine(pg_url)

# Загружаем метаданные
meta_sqlite = MetaData()
meta_pg = MetaData()

meta_sqlite.reflect(bind=eng_sqlite)
meta_pg.reflect(bind=eng_pg)

# Список таблиц, которые хотим перенести
tables_to_copy = ["user", "message", "poll", "vote"]

with eng_sqlite.connect() as conn_sqlite, eng_pg.connect() as conn_pg:
    for table_name in tables_to_copy:
        if table_name not in meta_sqlite.tables:
            print(f"❌ Таблица {table_name} не найдена в SQLite, пропускаем.")
            continue
        if table_name not in meta_pg.tables:
            print(f"❌ Таблица {table_name} не найдена в PostgreSQL, пропускаем.")
            continue

        table_sqlite = Table(table_name, meta_sqlite, autoload_with=eng_sqlite)
        table_pg = Table(table_name, meta_pg, autoload_with=eng_pg)

        # Данные из SQLite
        rows = conn_sqlite.execute(select(table_sqlite)).mappings().all()

        if not rows:
            print(f"ℹ️ Таблица {table_name} пуста, пропускаем.")
            continue

        # Получаем уже существующие ID в PostgreSQL
        existing_ids = {r[0] for r in conn_pg.execute(select(table_pg.c.id))}
        # Фильтруем только новые строки
        new_rows = [r for r in rows if r['id'] not in existing_ids]

        if new_rows:
            conn_pg.execute(insert(table_pg), new_rows)
            print(f"✅ Скопировано {len(new_rows)} новых строк в {table_name}")
        else:
            print(f"ℹ️ В {table_name} нет новых данных для копирования.")

print("🎉 Миграция завершена!")
