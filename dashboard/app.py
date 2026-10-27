"""Dashboard DVF : serveur web (API JSON + pages statiques), sans dépendance en plus de pandas.
Lancement : python dashboard/app.py   puis ouvrir http://localhost:8000
"""
import json
import sqlite3
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "dvf.db"
WEB = Path(__file__).resolve().parent / "static"
PORT = 8000

QUERY = """
SELECT d.date, d.annee, d.mois, l.code_commune, l.nom_commune, l.code_departement,
       t.type_local, f.valeur_fonciere AS prix, f.surface_reelle_bati AS surface,
       f.nombre_pieces AS pieces, f.surface_terrain AS terrain, f.prix_m2, f.latitude, f.longitude
FROM fact_ventes f
JOIN dim_date d USING (date_id)
JOIN dim_localisation l USING (localisation_id)
JOIN dim_type_bien t USING (type_bien_id)
"""
if not DB.exists():
    raise SystemExit("Base introuvable : lance d'abord python run_all.py")
with sqlite3.connect(DB) as con:
    DF = pd.read_sql_query(QUERY, con, parse_dates=["date"])

YEARS = sorted(int(y) for y in DF.annee.unique())
FILTERS = {
    "years": YEARS,
    "last": DF.date.max().strftime("%d/%m/%Y"),
    "types": sorted(DF.type_local.unique().tolist()),
    "depts": sorted(DF.code_departement.unique().tolist()),
    "communes": [{"code": r.code_commune, "nom": r.nom_commune, "dept": r.code_departement}
                 for r in DF[["code_commune", "nom_commune", "code_departement"]]
                 .drop_duplicates("code_commune").sort_values("nom_commune").itertuples()],
}


def num(x, d=0):
    return None if x is None or pd.isna(x) else round(float(x), d)


def filt(q, use_years=True):
    g = lambda k: q.get(k, [""])[0]  # noqa: E731
    d = DF
    if use_years and g("years"):
        d = d[d.annee.isin([int(y) for y in g("years").split(",")])]
    if g("type"):
        d = d[d.type_local == g("type")]
    if g("dept"):
        d = d[d.code_departement == g("dept")]
    if g("commune"):
        d = d[d.code_commune == g("commune")]
    if g("pieces"):
        p = int(g("pieces"))
        d = d[d.pieces >= 5] if p >= 5 else d[d.pieces == p]
    if g("smin"):
        d = d[d.surface >= float(g("smin"))]
    if g("smax"):
        d = d[d.surface <= float(g("smax"))]
    return d


def stats(q):
    d, dy = filt(q), filt(q, False)
    yr = dy.groupby("annee").agg(n=("prix_m2", "size"), p=("prix_m2", "median")).sort_index()
    yearly, prev = [], None
    for a, r in yr.iterrows():
        evo = num((r.p / prev - 1) * 100, 1) if prev else None
        yearly.append({"annee": int(a), "n": int(r.n), "prix_m2": num(r.p), "evo": evo})
        prev = r.p
    ys = sorted(int(y) for y in d.annee.unique())
    evo = next((y["evo"] for y in yearly if ys and y["annee"] == ys[-1]), None)
    m = d.groupby(["annee", "mois"]).prix_m2.median()
    monthly = {str(y): [num(m.get((y, k))) for k in range(1, 13)] for y in ys}
    gd = d.groupby("code_departement").agg(n=("prix_m2", "size"), p=("prix_m2", "median")).sort_index()
    gc = (d.groupby(["code_commune", "nom_commune"])
           .agg(n=("prix_m2", "size"), p=("prix_m2", "median"), la=("latitude", "mean"), lo=("longitude", "mean"))
           .reset_index())
    top = gc[gc.n >= 30]
    if len(top) < 5:
        top = gc[gc.n >= 5]
    sales = d.sort_values("date", ascending=False).head(12)
    yrs_all = sorted(int(y) for y in dy.annee.unique())
    dps = sorted(dy.code_departement.unique().tolist())
    tm = dy.groupby(["code_departement", "annee"]).agg(n=("prix_m2", "size"), p=("prix_m2", "median"))
    dtot = dy.groupby("code_departement").agg(n=("prix_m2", "size"), p=("prix_m2", "median"))
    ct = d.groupby(["code_departement", "type_local"]).size().unstack(fill_value=0)
    yt = dy.groupby(["annee", "type_local"]).size().unstack(fill_value=0)
    N = max(len(d), 1)
    tile = lambda label, mask: {"label": label, "pct": num(int(mask.sum()) / N * 100, 0), "n": int(mask.sum())}  # noqa: E731
    ms = d.groupby(["annee", "mois"]).agg(n=("prix_m2", "size"), p=("prix_m2", "median"),
                                          v=("prix", "median"), s=("surface", "median"))
    ex = {
        "matrix": {"years": yrs_all,
                   "rows": [{"dept": dp, "p": [num(tm.p.get((dp, y))) for y in yrs_all],
                             "n": [int(tm.n.get((dp, y), 0)) for y in yrs_all],
                             "tp": num(dtot.p.get(dp)), "tn": int(dtot.n.get(dp, 0))} for dp in dps],
                   "ty": [{"y": y["annee"], "p": y["prix_m2"], "n": y["n"]} for y in yearly]},
        "bytype": {"depts": ct.index.tolist(), **{t: ct[t].astype(int).tolist() for t in ct.columns}},
        "ytype": {"years": [int(i) for i in yt.index], **{t: yt[t].astype(int).tolist() for t in yt.columns}},
        "pieces": {str(int(k)): int(v) for k, v in d.pieces.clip(upper=5).value_counts().sort_index().items()},
        "tiles": [tile("Appartements", d.type_local == "Appartement"), tile("Maisons", d.type_local == "Maison"),
                  tile("Avec terrain", d.terrain > 0), tile("4 pièces et +", d.pieces >= 4),
                  tile("Moins de 50 m²", d.surface < 50), tile("Plus de 500 k€", d.prix >= 500000)],
        "spark": {c: [num(x) for x in ms[c]] for c in ["n", "p", "v", "s"]},
    }
    return {
        **ex,
        "kpi": {"n": len(d), "prix_m2": num(d.prix_m2.median()), "prix": num(d.prix.median()),
                "surface": num(d.surface.median()), "evo": evo, "annee": ys[-1] if ys else None},
        "share": {k: int(v) for k, v in d.type_local.value_counts().items()},
        "monthly": monthly, "yearly": yearly,
        "depts": [{"dept": i, "n": int(r.n), "prix_m2": num(r.p)} for i, r in gd.iterrows()],
        "top": [{"nom": r.nom_commune, "n": int(r.n), "prix_m2": num(r.p)} for r in top.nlargest(10, "p").itertuples()],
        "map": [{"code": r.code_commune, "nom": r.nom_commune, "n": int(r.n), "prix_m2": num(r.p),
                 "la": num(r.la, 4), "lo": num(r.lo, 4)} for r in gc[gc.n >= 5].itertuples()],
        "sales": [{"commune": r.nom_commune, "type": r.type_local, "surface": num(r.surface),
                   "pieces": int(r.pieces), "prix": num(r.prix), "prix_m2": num(r.prix_m2),
                   "date": r.date.strftime("%d/%m/%Y")} for r in sales.itertuples()],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/filters":
                return self.send(json.dumps(FILTERS).encode(), "application/json")
            if u.path == "/api/stats":
                return self.send(json.dumps(stats(parse_qs(u.query))).encode(), "application/json")
            f = WEB / ("index.html" if u.path in ("/", "") else u.path.lstrip("/"))
            if f.resolve().parent != WEB.resolve() or not f.is_file():
                return self.send(b"404", "text/plain", 404)
            ctype = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml"}.get(f.suffix, "text/plain")
            return self.send(f.read_bytes(), ctype)
        except Exception as e:  # noqa: BLE001
            return self.send(json.dumps({"error": str(e)}).encode(), "application/json", 500)


if __name__ == "__main__":
    print(f"{len(DF):,} ventes chargées | années disponibles : {YEARS}".replace(",", " "))
    if len(YEARS) < 2:
        print("ATTENTION : une seule année dans la base, la comparaison entre années sera vide.")
    print(f"Dashboard : http://localhost:{PORT}  (Ctrl+C pour arrêter)")
    threading.Timer(1, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
