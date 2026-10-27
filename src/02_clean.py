"""Étape 2 : nettoyage des données DVF brutes -> data/processed/ventes_propres.csv

Règles appliquées (chaque étape affiche le nombre de lignes restantes) :
  1. on garde les ventes (nature_mutation = « Vente ») d'appartements et de maisons ;
  2. on supprime les doublons dus aux parcelles multiples d'un même bien ;
  3. on garde les mutations à un seul bien (sinon le prix est celui d'un lot de biens) ;
  4. on supprime les lignes incomplètes et les valeurs aberrantes ;
  5. on calcule le prix au m².
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "ventes_propres.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)

COLS = [
    "id_mutation", "date_mutation", "nature_mutation", "valeur_fonciere",
    "code_postal", "code_commune", "nom_commune", "code_departement",
    "type_local", "surface_reelle_bati", "nombre_pieces_principales",
    "surface_terrain", "longitude", "latitude",
]
TYPES = ["Appartement", "Maison"]

# Bornes de filtrage des valeurs aberrantes (à ajuster et à documenter dans le README)
VALEUR_MIN, VALEUR_MAX = 20_000, 5_000_000
SURFACE_MIN, SURFACE_MAX = 9, 400
PRIX_M2_MIN, PRIX_M2_MAX = 1_000, 25_000
PIECES_MIN, PIECES_MAX = 1, 10


def load_raw() -> pd.DataFrame:
    files = sorted(RAW.glob("*.csv*"))
    if not files:
        raise SystemExit("Aucun fichier dans data/raw/ : lance d'abord 01_download.py")
    frames = []
    for f in files:
        header = pd.read_csv(f, nrows=0).columns
        usecols = [c for c in COLS if c in header]
        frames.append(
            pd.read_csv(
                f,
                usecols=usecols,
                dtype={"id_mutation": str, "code_commune": str,
                       "code_departement": str, "code_postal": str},
                low_memory=False,
            )
        )
        print(f"  lu : {f.name}")
    return pd.concat(frames, ignore_index=True)


def log(label: str, df: pd.DataFrame) -> None:
    print(f"  {label:<55} {len(df):>10,}".replace(",", " "))


def main() -> None:
    df = load_raw()
    print()
    log("lignes brutes", df)

    df = df[df["nature_mutation"] == "Vente"]
    log("après filtre « Vente »", df)

    df = df[df["type_local"].isin(TYPES)].copy()
    log("après filtre appartements / maisons", df)

    # Un même bien peut apparaître plusieurs fois (une ligne par parcelle) :
    # on regroupe en additionnant la surface de terrain.
    for c in ["valeur_fonciere", "surface_reelle_bati", "nombre_pieces_principales",
              "surface_terrain", "longitude", "latitude"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    key = ["id_mutation", "type_local", "surface_reelle_bati",
           "nombre_pieces_principales", "valeur_fonciere"]
    df["surface_terrain"] = df.groupby(key, dropna=False)["surface_terrain"].transform("sum")
    df = df.drop_duplicates(subset=key)
    log("après suppression des doublons de parcelles", df)

    # Mutations à un seul bien (le prix correspond alors bien à ce bien)
    n_biens = df.groupby("id_mutation")["id_mutation"].transform("size")
    df = df[n_biens == 1]
    log("après mutations à un seul bien", df)

    df["date_mutation"] = pd.to_datetime(df["date_mutation"], errors="coerce")
    df = df.dropna(subset=["valeur_fonciere", "surface_reelle_bati", "date_mutation",
                           "nombre_pieces_principales", "latitude", "longitude",
                           "code_commune", "nom_commune"])
    log("après suppression des lignes incomplètes", df)

    df = df[df["valeur_fonciere"].between(VALEUR_MIN, VALEUR_MAX)]
    df = df[df["surface_reelle_bati"].between(SURFACE_MIN, SURFACE_MAX)]
    df = df[df["nombre_pieces_principales"].between(PIECES_MIN, PIECES_MAX)]
    df["prix_m2"] = (df["valeur_fonciere"] / df["surface_reelle_bati"]).round(2)
    df = df[df["prix_m2"].between(PRIX_M2_MIN, PRIX_M2_MAX)]
    log("après filtrage des valeurs aberrantes", df)

    df["nombre_pieces_principales"] = df["nombre_pieces_principales"].astype(int)
    df["annee"] = df["date_mutation"].dt.year
    df["mois"] = df["date_mutation"].dt.month
    df = df.drop(columns=["nature_mutation"]).reset_index(drop=True)

    df.to_csv(OUT, index=False)
    print(f"\nFichier propre enregistré : {OUT} ({len(df):,} lignes)".replace(",", " "))


if __name__ == "__main__":
    main()
