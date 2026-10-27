"""Étape 4 : exécute les requêtes de sql/analyses.sql et exporte les résultats en CSV."""
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "dvf.db"
SQL_FILE = ROOT / "sql" / "analyses.sql"
EXPORT = ROOT / "exports"
EXPORT.mkdir(exist_ok=True)


def main() -> None:
    if not DB.exists():
        raise SystemExit("Base introuvable : lance d'abord 03_build_db.py")
    text = SQL_FILE.read_text(encoding="utf-8")
    blocks = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    # blocks = [préambule, nom1, sql1, nom2, sql2, ...]
    with sqlite3.connect(DB) as con:
        for name, sql in zip(blocks[1::2], blocks[2::2]):
            df = pd.read_sql_query(sql, con)
            df.to_csv(EXPORT / f"{name}.csv", index=False)
            print(f"\n=== {name} ({len(df)} lignes) ===")
            print(df.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
