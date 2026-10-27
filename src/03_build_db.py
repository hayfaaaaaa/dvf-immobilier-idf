"""Étape 3 : chargement dans une base SQLite avec un modèle en étoile.

        dim_date ──┐
 dim_localisation ─┼── fact_ventes
    dim_type_bien ─┘

Exporte aussi chaque table en CSV (exports/powerbi/) pour Power BI.
"""
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "processed" / "ventes_propres.csv"
DB = ROOT / "db" / "dvf.db"
EXPORT = ROOT / "exports" / "powerbi"
DB.parent.mkdir(parents=True, exist_ok=True)
EXPORT.mkdir(parents=True, exist_ok=True)

DDL = """
DROP TABLE IF EXISTS fact_ventes;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_localisation;
DROP TABLE IF EXISTS dim_type_bien;

CREATE TABLE dim_date (
    date_id     INTEGER PRIMARY KEY,   -- format AAAAMMJJ
    date        TEXT NOT NULL,         -- AAAA-MM-JJ
    annee       INTEGER NOT NULL,
    trimestre   INTEGER NOT NULL,
    mois        INTEGER NOT NULL,
    annee_mois  TEXT NOT NULL          -- AAAA-MM
);
CREATE TABLE dim_localisation (
    localisation_id  INTEGER PRIMARY KEY,
    code_commune     TEXT NOT NULL UNIQUE,
    nom_commune      TEXT NOT NULL,
    code_departement TEXT NOT NULL
);
CREATE TABLE dim_type_bien (
    type_bien_id INTEGER PRIMARY KEY,
    type_local   TEXT NOT NULL UNIQUE
);
CREATE TABLE fact_ventes (
    vente_id            INTEGER PRIMARY KEY,
    id_mutation         TEXT NOT NULL,
    date_id             INTEGER NOT NULL REFERENCES dim_date(date_id),
    localisation_id     INTEGER NOT NULL REFERENCES dim_localisation(localisation_id),
    type_bien_id        INTEGER NOT NULL REFERENCES dim_type_bien(type_bien_id),
    valeur_fonciere     REAL NOT NULL,
    surface_reelle_bati REAL NOT NULL,
    nombre_pieces       INTEGER NOT NULL,
    surface_terrain     REAL NOT NULL,
    prix_m2             REAL NOT NULL,
    latitude            REAL NOT NULL,
    longitude           REAL NOT NULL
);
CREATE INDEX idx_fact_date ON fact_ventes(date_id);
CREATE INDEX idx_fact_loc  ON fact_ventes(localisation_id);
CREATE INDEX idx_fact_type ON fact_ventes(type_bien_id);
"""


def main() -> None:
    if not CSV.exists():
        raise SystemExit("Fichier propre introuvable : lance d'abord 02_clean.py")
    df = pd.read_csv(CSV, dtype={"code_commune": str, "code_departement": str},
                     parse_dates=["date_mutation"])

    # --- dimensions ---
    jours = pd.date_range(df["date_mutation"].min().normalize(),
                          df["date_mutation"].max().normalize(), freq="D")
    dim_date = pd.DataFrame({"date": jours})
    dim_date["date_id"] = dim_date["date"].dt.strftime("%Y%m%d").astype(int)
    dim_date["annee"] = dim_date["date"].dt.year
    dim_date["trimestre"] = dim_date["date"].dt.quarter
    dim_date["mois"] = dim_date["date"].dt.month
    dim_date["annee_mois"] = dim_date["date"].dt.strftime("%Y-%m")
    dim_date["date"] = dim_date["date"].dt.strftime("%Y-%m-%d")
    dim_date = dim_date[["date_id", "date", "annee", "trimestre", "mois", "annee_mois"]]

    dim_loc = (df[["code_commune", "nom_commune", "code_departement"]]
               .drop_duplicates("code_commune").sort_values("code_commune")
               .reset_index(drop=True))
    dim_loc.insert(0, "localisation_id", dim_loc.index + 1)

    dim_type = (pd.DataFrame({"type_local": sorted(df["type_local"].unique())})
                .reset_index(drop=True))
    dim_type.insert(0, "type_bien_id", dim_type.index + 1)

    # --- table de faits ---
    fact = (df.merge(dim_loc[["localisation_id", "code_commune"]], on="code_commune")
              .merge(dim_type, on="type_local"))
    fact["date_id"] = fact["date_mutation"].dt.strftime("%Y%m%d").astype(int)
    fact = fact.rename(columns={"nombre_pieces_principales": "nombre_pieces"})
    fact = fact[["id_mutation", "date_id", "localisation_id", "type_bien_id",
                 "valeur_fonciere", "surface_reelle_bati", "nombre_pieces",
                 "surface_terrain", "prix_m2", "latitude", "longitude"]].reset_index(drop=True)
    fact.insert(0, "vente_id", fact.index + 1)

    # --- chargement ---
    with sqlite3.connect(DB) as con:
        con.executescript(DDL)
        dim_date.to_sql("dim_date", con, if_exists="append", index=False)
        dim_loc.to_sql("dim_localisation", con, if_exists="append", index=False)
        dim_type.to_sql("dim_type_bien", con, if_exists="append", index=False)
        fact.to_sql("fact_ventes", con, if_exists="append", index=False)
        for t in ["dim_date", "dim_localisation", "dim_type_bien", "fact_ventes"]:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t:<18} {n:>10,} lignes".replace(",", " "))

    # --- exports CSV pour Power BI ---
    dim_date.to_csv(EXPORT / "dim_date.csv", index=False)
    dim_loc.to_csv(EXPORT / "dim_localisation.csv", index=False)
    dim_type.to_csv(EXPORT / "dim_type_bien.csv", index=False)
    fact.to_csv(EXPORT / "fact_ventes.csv", index=False)
    print(f"\nBase créée : {DB}\nCSV Power BI : {EXPORT}")


if __name__ == "__main__":
    main()
