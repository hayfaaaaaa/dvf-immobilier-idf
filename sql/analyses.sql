-- Requêtes d'analyse sur le modèle en étoile (SQLite).
-- Chaque bloc « -- name: xxx » est exécuté par src/04_sql_analysis.py
-- et exporté dans exports/xxx.csv

-- name: prix_m2_median_par_commune
-- Médiane du prix au m² par commune (communes avec au moins 30 ventes).
-- SQLite n'a pas de fonction MEDIAN : on la calcule avec des fonctions de fenêtrage.
WITH ranked AS (
    SELECT l.code_commune, l.nom_commune, l.code_departement, f.prix_m2,
           ROW_NUMBER() OVER (PARTITION BY l.code_commune ORDER BY f.prix_m2) AS rn,
           COUNT(*)     OVER (PARTITION BY l.code_commune)                    AS n
    FROM fact_ventes f
    JOIN dim_localisation l USING (localisation_id)
)
SELECT code_commune, nom_commune, code_departement,
       n AS nb_ventes,
       ROUND(AVG(prix_m2), 0) AS prix_m2_median
FROM ranked
WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY code_commune, nom_commune, code_departement, n
HAVING n >= 30
ORDER BY prix_m2_median DESC;

-- name: evolution_mensuelle
-- Nombre de ventes et prix moyen au m² par mois et par type de bien.
SELECT d.annee_mois, t.type_local,
       COUNT(*)                  AS nb_ventes,
       ROUND(AVG(f.prix_m2), 0)  AS prix_m2_moyen
FROM fact_ventes f
JOIN dim_date d      USING (date_id)
JOIN dim_type_bien t USING (type_bien_id)
GROUP BY d.annee_mois, t.type_local
ORDER BY d.annee_mois, t.type_local;

-- name: prix_m2_median_departement_type_annee
-- Médiane du prix au m² par département, type de bien et année.
WITH ranked AS (
    SELECT l.code_departement, t.type_local, d.annee, f.prix_m2,
           ROW_NUMBER() OVER (PARTITION BY l.code_departement, t.type_local, d.annee
                              ORDER BY f.prix_m2) AS rn,
           COUNT(*)     OVER (PARTITION BY l.code_departement, t.type_local, d.annee) AS n
    FROM fact_ventes f
    JOIN dim_localisation l USING (localisation_id)
    JOIN dim_type_bien t    USING (type_bien_id)
    JOIN dim_date d         USING (date_id)
)
SELECT code_departement, type_local, annee, n AS nb_ventes,
       ROUND(AVG(prix_m2), 0) AS prix_m2_median
FROM ranked
WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY code_departement, type_local, annee, n
ORDER BY code_departement, type_local, annee;

-- name: top20_communes_par_volume
-- Les 20 communes avec le plus de ventes.
SELECT l.nom_commune, l.code_departement,
       COUNT(*)                       AS nb_ventes,
       ROUND(AVG(f.valeur_fonciere), 0) AS prix_moyen,
       ROUND(AVG(f.surface_reelle_bati), 1) AS surface_moyenne
FROM fact_ventes f
JOIN dim_localisation l USING (localisation_id)
GROUP BY l.code_commune, l.nom_commune, l.code_departement
ORDER BY nb_ventes DESC
LIMIT 20;
