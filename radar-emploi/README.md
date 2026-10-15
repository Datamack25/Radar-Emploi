# Radar Emploi 3

Veille d'offres d'emploi **juniors (0 à 3 ans)**, **en France uniquement**, pour :

- conformité, LCB-FT, KYC, sanctions et embargos ;
- business analyst sur un sujet KYC, LCB-FT ou conformité ;
- analyste crédit **ouvert aux débutants**.

Seules les offres en **CDI**, ou en **CDD / intérim d'au moins 3 mois**, sont retenues. Une offre qui affiche un salaire
**inférieur à 33 k€ brut annuel** est écartée. Une offre sans salaire affiché est gardée.

Sources : API France Travail, API Adzuna (index France), sites carrières lisibles par API publique (Greenhouse, Lever,
Ashby, SmartRecruiters, Workable, Recruitee). Pour LinkedIn, Indeed, WTTJ, APEC, HelloWork et Jobteaser, l'application
fournit des recherches pré-remplies que vous ouvrez vous-même.

## Lancer en local

1. Copiez `.env.example` en `.env` et renseignez au moins `FT_CLIENT_ID` et `FT_CLIENT_SECRET`.
2. Double-cliquez sur `lancer.bat` (Windows) ou lancez `./lancer.sh` (Mac / Linux).
   À défaut, exécutez `pip install -r requirements.txt` puis `streamlit run app.py`.

## Streamlit Cloud

Poussez le dossier sur GitHub sans `.env`. Les fichiers obligatoires sont `app.py`, `requirements.txt`, `core/` et `config/`.
Collez ensuite les clés dans *Settings → Secrets*, au format de `.streamlit/secrets.toml.example`, puis faites *Reboot app*.

## Clés France Travail

1. Sur francetravail.io, ouvrez « Mes applications » et créez une application.
2. Abonnez-la à l'API **Offres d'emploi v2**.
3. Copiez l'identifiant et la clé secrète dans `.env` ou dans les secrets.

L'onglet « Sources & diagnostic » indique, pour chaque clé, si elle a été trouvée.

## Personnaliser

- `config/profil.toml` : mots-clés, expérience maximale, salaire minimum, contrats et durée minimale, fraîcheur.
- `config/employeurs.csv` : annuaire des employeurs (`nom;categorie;site;ats;token;alias`).

Les offres et votre suivi des candidatures sont enregistrés dans `data/radar3.db`.
