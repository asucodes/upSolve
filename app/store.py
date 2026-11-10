import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect():
    path = Path(os.environ.get("UPSOLVE_DB", "data/upsolve.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id))"
    )
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def put(db, kind, id, body):
    db.execute(
        "INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body",
        (kind, id.lower(), json.dumps(body)),
    )


def get(db, kind, id, default=None):
    row = db.execute(
        "SELECT body FROM records WHERE kind=? AND id=?", (kind, id.lower())
    ).fetchone()
    return json.loads(row[0]) if row else default


def all_records(db, kind):
    return [
        json.loads(r[0])
        for r in db.execute("SELECT body FROM records WHERE kind=?", (kind,))
    ]
