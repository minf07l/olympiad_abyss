# migrate_db.py
import os, json, datetime
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, MetaData, Table, select, insert
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sqlite_path = os.path.join(BASE_DIR, 'instance', 'app.db')
sqlite_url = f"sqlite:///{sqlite_path}"

pg_url = os.environ.get('DATABASE_URL') or ''
if pg_url.startswith('postgres://'):
    pg_url = pg_url.replace('postgres://', 'postgresql://', 1)

if not os.path.exists(sqlite_path):
    print("SQLite file not found:", sqlite_path)
    raise SystemExit(1)
if not pg_url:
    print("Set DATABASE_URL env var to target Postgres database (Render).")
    raise SystemExit(1)

# engines
eng_sqlite = create_engine(sqlite_url)
eng_pg = create_engine(pg_url)

meta_sqlite = MetaData(bind=eng_sqlite)
meta_pg = MetaData(bind=eng_pg)

meta_sqlite.reflect(only=['user','message','poll','vote'])
meta_pg.reflect()

SessionPG = sessionmaker(bind=eng_pg)
sess_pg = SessionPG()

# helper to copy table rows
def copy_table(tbl_name, key_cols=None):
    print("Copying:", tbl_name)
    t_sql = Table(tbl_name, meta_sqlite, autoload_with=eng_sqlite)
    t_pg = Table(tbl_name, meta_pg, autoload_with=eng_pg)
    rows = eng_sqlite.execute(select(t_sql)).fetchall()
    for r in rows:
        rowdict = dict(r._mapping)
        # skip primary key so Postgres will auto-assign? we try to keep ids if possible
        # try to avoid duplicates for users by username
        if tbl_name == 'user':
            existing = sess_pg.execute(select(t_pg).where(t_pg.c.username==rowdict['username'])).fetchone()
            if existing:
                print(" - user exists, skipping:", rowdict['username'])
                continue
        try:
            sess_pg.execute(insert(t_pg).values(**rowdict))
        except Exception as e:
            # on primary key conflicts or other, try inserting without id if id causes conflict
            sess_pg.rollback()
            # remove id if present
            if 'id' in rowdict:
                row_noid = {k:v for k,v in rowdict.items() if k!='id'}
                try:
                    sess_pg.execute(insert(t_pg).values(**row_noid))
                except Exception as e2:
                    sess_pg.rollback()
                    print("  failed to insert row (skipped):", e2)
            else:
                print("  failed to insert row (skipped):", e)
        else:
            sess_pg.commit()

# copy in order to maintain FK integrity
for name in ('user','message','poll','vote'):
    if name in meta_sqlite.tables and name in meta_pg.tables:
        copy_table(name)
    else:
        print(" - table missing in sqlite or pg:", name)

print("Migration complete.")
