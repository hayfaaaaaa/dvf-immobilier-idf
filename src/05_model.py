"""Étape 5 : modèles de prédiction du prix d'un bien.

Cible : valeur_fonciere (en €), apprise sur log(1 + prix) puis reconvertie en euros.
Modèles comparés : référence (médiane), régression linéaire, Random Forest,
Gradient Boosting (HistGradientBoosting).
Évaluation sur 20 % des ventes mises de côté (RMSE, MAE, R², erreur relative médiane).
"""
import json
import sqlite3
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "dvf.db"
REPORTS = ROOT / "reports"
FIG = REPORTS / "figures"
MODELS = ROOT / "models"
EXPORT = ROOT / "exports" / "powerbi"
for p in (FIG, MODELS, EXPORT):
    p.mkdir(parents=True, exist_ok=True)

SEED = 42
MAX_TRAIN_ROWS_RF = 300_000  # limite pour garder un temps de calcul raisonnable

NUM = ["surface_reelle_bati", "nombre_pieces", "surface_terrain",
       "latitude", "longitude", "annee", "mois"]
CAT = ["type_local", "code_departement"]

QUERY = """
SELECT f.valeur_fonciere, f.surface_reelle_bati, f.nombre_pieces, f.surface_terrain,
       f.latitude, f.longitude, t.type_local, l.code_departement, l.nom_commune,
       d.annee, d.mois
FROM fact_ventes f
JOIN dim_type_bien t     USING (type_bien_id)
JOIN dim_localisation l  USING (localisation_id)
JOIN dim_date d          USING (date_id)
"""


def make_pipeline(estimator, scale: bool) -> TransformedTargetRegressor:
    num_tf = StandardScaler() if scale else "passthrough"
    pre = ColumnTransformer([
        ("num", num_tf, NUM),
        ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CAT),
    ])
    return TransformedTargetRegressor(
        regressor=Pipeline([("pre", pre), ("model", estimator)]),
        func=np.log1p, inverse_func=np.expm1,
    )


def evaluate(y_true, y_pred) -> dict:
    return {
        "RMSE (€)": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "MAE (€)": float(mean_absolute_error(y_true, y_pred)),
        "R2": float(r2_score(y_true, y_pred)),
        "Erreur relative médiane (%)": float(np.median(np.abs(y_pred - y_true) / y_true) * 100),
    }


def main() -> None:
    if not DB.exists():
        raise SystemExit("Base introuvable : lance d'abord 03_build_db.py")
    with sqlite3.connect(DB) as con:
        df = pd.read_sql_query(QUERY, con)
    print(f"{len(df):,} ventes chargées depuis la base".replace(",", " "))

    X, y = df[NUM + CAT + ["nom_commune"]], df["valeur_fonciere"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=SEED)
    print(f"entraînement : {len(X_tr):,} | test : {len(X_te):,}".replace(",", " "))

    models = {
        "Référence (médiane)": make_pipeline(DummyRegressor(strategy="median"), scale=False),
        "Régression linéaire": make_pipeline(LinearRegression(), scale=True),
        "Random Forest": make_pipeline(
            RandomForestRegressor(n_estimators=150, min_samples_leaf=5,
                                  n_jobs=-1, random_state=SEED), scale=False),
        "Gradient Boosting": make_pipeline(
            HistGradientBoostingRegressor(max_iter=300, learning_rate=0.1,
                                          random_state=SEED), scale=False),
    }

    results, fitted = {}, {}
    for name, model in models.items():
        Xt, yt = X_tr[NUM + CAT], y_tr
        if name == "Random Forest" and len(Xt) > MAX_TRAIN_ROWS_RF:
            idx = Xt.sample(MAX_TRAIN_ROWS_RF, random_state=SEED).index
            Xt, yt = Xt.loc[idx], yt.loc[idx]
        model.fit(Xt, yt)
        pred = model.predict(X_te[NUM + CAT])
        results[name] = evaluate(y_te.values, pred)
        fitted[name] = (model, pred)
        r = results[name]
        print(f"  {name:<22} RMSE {r['RMSE (€)']:>10,.0f} € | MAE {r['MAE (€)']:>9,.0f} € | "
              f"R² {r['R2']:.3f} | err. rel. médiane {r['Erreur relative médiane (%)']:.1f} %"
              .replace(",", " "))

    best = min((n for n in results if n != "Référence (médiane)"),
               key=lambda n: results[n]["RMSE (€)"])
    best_model, best_pred = fitted[best]
    print(f"\nMeilleur modèle : {best}")

    # --- sauvegardes ---
    joblib.dump(best_model, MODELS / "meilleur_modele.joblib")
    (REPORTS / "metrics.json").write_text(
        json.dumps({"meilleur_modele": best, "resultats": results,
                    "n_train": len(X_tr), "n_test": len(X_te)}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    (REPORTS / "metrics.txt").write_text(pd.DataFrame(results).T.round(3).to_string(),
                                         encoding="utf-8")

    # --- figure 1 : prédit vs réel ---
    sample = np.random.RandomState(SEED).choice(len(y_te), size=min(4000, len(y_te)), replace=False)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y_te.values[sample] / 1e3, best_pred[sample] / 1e3, s=6, alpha=0.35)
    lim = max(y_te.values[sample].max(), best_pred[sample].max()) / 1e3
    ax.plot([0, lim], [0, lim], "r--", lw=1)
    ax.set_xlabel("Prix réel (k€)")
    ax.set_ylabel("Prix prédit (k€)")
    ax.set_title(f"{best} : prix prédit vs prix réel (échantillon test)")
    fig.tight_layout()
    fig.savefig(FIG / "predit_vs_reel.png", dpi=150)
    plt.close(fig)

    # --- figure 2 : importance des variables ---
    idx = np.random.RandomState(SEED).choice(len(X_te), size=min(5000, len(X_te)), replace=False)
    Xs, ys = X_te[NUM + CAT].iloc[idx], y_te.iloc[idx]
    imp = permutation_importance(best_model, Xs, ys, n_repeats=3, random_state=SEED,
                                 scoring="r2", n_jobs=-1)
    imp_df = (pd.DataFrame({"variable": NUM + CAT, "importance": imp.importances_mean})
              .sort_values("importance"))
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(imp_df["variable"], imp_df["importance"])
    ax.set_xlabel("Baisse du R² si la variable est mélangée")
    ax.set_title("Importance des variables (permutation)")
    fig.tight_layout()
    fig.savefig(FIG / "importance_variables.png", dpi=150)
    plt.close(fig)
    imp_df.sort_values("importance", ascending=False).to_csv(
        EXPORT / "importance_variables.csv", index=False)

    # --- export des prédictions pour Power BI ---
    out = X_te[["nom_commune", "code_departement", "type_local",
                "surface_reelle_bati", "nombre_pieces"]].copy()
    out["prix_reel"] = y_te.values
    out["prix_predit"] = best_pred.round(0)
    out["erreur_pct"] = ((out["prix_predit"] - out["prix_reel"]) / out["prix_reel"] * 100).round(1)
    out.to_csv(EXPORT / "predictions_test.csv", index=False)
    print(f"\nFigures : {FIG}\nModèle : {MODELS / 'meilleur_modele.joblib'}")


if __name__ == "__main__":
    main()
