"""Radar Emploi 3 — offres conformité / LCB-FT / KYC / sanctions, business analyst conformité et analyste crédit,
juniors (0 à 3 ans), France uniquement, CDI ou CDD / intérim d'au moins 3 mois, salaire ≥ 33 k€.

Lancement : streamlit run app.py  (ou lancer.bat / lancer.sh)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

# --- Contrôle du dépôt : Streamlit Cloud masque les erreurs d'import, on les explique nous-mêmes ---
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
REQUIRED = ["core/__init__.py", "core/annuaire.py", "core/config.py", "core/filters.py", "core/geo.py", "core/http.py",
            "core/pipeline.py", "core/scoring.py", "core/store.py", "core/text.py", "core/ui_html.py",
            "core/sources/__init__.py", "core/sources/france_travail.py", "core/sources/adzuna.py", "core/sources/ats.py",
            "core/sources/google_jobs.py", "core/sources/jooble.py",
            "core/sources/liens.py", "config/profil.toml", "config/employeurs.csv"]
_missing = [p for p in REQUIRED if not (ROOT / p).exists()]
if _missing:
    st.set_page_config(page_title="Radar Emploi — installation incomplète", page_icon="⚠️")
    st.error("Installation incomplète : des fichiers de l'application sont absents.")
    st.code("\n".join(_missing))
    st.markdown("Les dossiers **`core/`** (avec `core/sources/`) et **`config/`** doivent être à côté de `app.py` (voir README).")
    st.stop()

# --- Clés : fichier .env (local), puis secrets Streamlit (local ou Cloud), au premier niveau ou dans une section ---
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _secret(k: str) -> str:
    try:
        if k in st.secrets:
            return str(st.secrets[k]).strip()
        for sec in st.secrets.values():
            if hasattr(sec, "get") and k in sec:
                return str(sec[k]).strip()
    except Exception:  # pas de fichier secrets : normal en local
        pass
    return ""


KEYS = ("FT_CLIENT_ID", "FT_CLIENT_SECRET", "SERPAPI_KEY", "JOOBLE_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "RADAR_CONTACT")
for _k in KEYS:
    if not os.environ.get(_k, "").strip():
        _v = _secret(_k)
        if _v:
            os.environ[_k] = _v
    else:
        os.environ[_k] = os.environ[_k].strip()

from core import ui_html as ui  # noqa: E402
from core.annuaire import CATEGORIES  # noqa: E402
from core.config import load_config  # noqa: E402
from core.filters import FAMILIES  # noqa: E402
from core.geo import REGION_NAMES  # noqa: E402
from core.http import Http, HttpError  # noqa: E402
from core.pipeline import ats_targets, run_update  # noqa: E402
from core.sources.ats import PARSERS, PUBLIC_PAGE, check_links, detect_ats, discover  # noqa: E402
from core.sources.liens import deep_links  # noqa: E402
from core.store import STATUSES, Store  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
SOURCE_NAMES = {"france_travail": "France Travail", "google": "Google Emploi", "jooble": "Jooble", "adzuna": "Adzuna",
                "ats": "Site carrières de l'employeur"}
PAGE = 12
NO_REGION = "Région non précisée"
CONTRACTS = ["CDI", "CDD", "Intérim", "Non précisé"]

st.set_page_config(page_title="Radar Emploi", page_icon="🎯", layout="wide")
cfg = load_config()
store = Store(cfg.db_path)
cand = cfg.candidat
SAL_MIN = int(cand.get("salaire_min_annuel", 33000))
EXP_MAX = int(cand.get("experience_max_ans", 3))
DUR_MIN = int(cand.get("duree_min_mois", 3))
st.html(ui.CSS)


# ------------------------------------------------------------------ utilitaires
def to_dt(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00")) if s else None
    except ValueError:
        return None
    if d and d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def fmt_dt(s) -> str:
    d = to_dt(s)
    return d.astimezone(PARIS).strftime("%d/%m/%Y à %H:%M") if d else "jamais"


def age_days(s):
    d = to_dt(s)
    return (datetime.now(timezone.utc) - d).total_seconds() / 86400 if d else None


def age_text(s) -> str:
    a = age_days(s)
    return "à une date inconnue" if a is None else "aujourd'hui" if a < 1 else f"il y a {int(a)} j"


def set_status(uid: str, k: str):
    r = store.get(uid)
    if r:
        store.set_user_fields(uid, st.session_state[k], r["notes"])


def new_http(delay=0.3):
    return lambda: Http(cfg.user_agent, delay=delay, retries=0)


def run_long(flag: str, label: str, job):
    """Exécute une tâche longue une seule fois, avec avancement visible, sans bloquer l'application."""
    try:
        with st.status(label, expanded=True) as box:
            res = job(lambda m: st.write(m))
            box.update(label="Terminé", state="complete", expanded=False)
        st.session_state[flag + "_result"] = res
    except Exception as exc:  # noqa: BLE001
        st.session_state["flash_error"] = f"{type(exc).__name__} : {exc}"
    finally:
        st.session_state[flag] = False
    st.rerun()


@st.dialog("Détail de l'offre", width="large")
def detail_dialog(uid: str):
    r = store.get(uid)
    if not r:
        st.warning("Offre introuvable.")
        return
    st.html(ui.offer_card(r, False, age_text(r["posted_at"]), SOURCE_NAMES.get(r["source"], r["source"])))
    b1, b2 = st.columns(2)
    b1.link_button("Candidater ↗", ui.safe_url(r["apply_url"] or r["url"]), type="primary", width="stretch")
    b2.link_button("Voir l'offre d'origine ↗", ui.safe_url(r["url"]), width="stretch")
    if r["also"]:
        st.caption("Aussi publiée sur : " + " · ".join(f"[{SOURCE_NAMES.get(a['source'], a['source'])}]({ui.safe_url(a['url'])})"
                                                      for a in r["also"]))
    st.markdown("**Texte de l'offre**")
    st.html(ui.description_html(r["description"]))
    ex = r["extra"]
    if r["source"] == "france_travail":
        src = (f"Source : France Travail{' (partenaire ' + ex['partenaire'] + ')' if ex.get('partenaire') else ''} · "
               f"dernière mise à jour : {fmt_dt(ex.get('mise_a_jour'))}"
               + (f" · salaire affiché : {ex['salaire_affiche']}" if ex.get("salaire_affiche") else "") + ".")
    elif r["source"] == "google":
        src = f"Source : Google Emploi{' — publiée via ' + ex['via'] if ex.get('via') else ''}."
        if ex.get("candidater"):
            st.caption("Où candidater : " + " · ".join(f"[{c['site'] or 'lien'}]({ui.safe_url(c['url'])})" for c in ex["candidater"]))
    elif r["source"] == "jooble":
        src = f"Source : Jooble{' — publiée sur ' + ex['via'] if ex.get('via') else ''} (extrait : texte complet sur le lien d'origine)."
    elif r["source"] == "adzuna":
        src = "Offre propulsée par Adzuna (extrait : texte complet sur le lien d'origine)."
    else:
        src = f"Source : site carrières de {r['company']} ({ex.get('ats', '')})." + (
            " Date de publication incertaine (date de mise à jour utilisée)." if ex.get("date_incertaine") else "")
    st.html(f'<div class="rc-source">{ui.esc(src)}</div>')
    if r["logo"]:
        st.image(r["logo"], width=110)
    st.markdown("**Pourquoi ce score**")
    st.html(ui.breakdown_html(r["breakdown"]))
    with st.form("suivi"):
        c1, c2 = st.columns([1, 2])
        status = c1.selectbox("Statut", STATUSES, index=STATUSES.index(r["status"]) if r["status"] in STATUSES else 0)
        notes = c2.text_area("Notes", value=r["notes"], height=90)
        if st.form_submit_button("Enregistrer le suivi", type="primary"):
            store.set_user_fields(uid, status, notes)
            st.rerun()


# ------------------------------------------------------------------ état
ft_ok = bool(os.environ.get("FT_CLIENT_ID") and os.environ.get("FT_CLIENT_SECRET"))
az_ok = bool(os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY"))
gg_ok = bool(os.environ.get("SERPAPI_KEY"))
jb_ok = bool(os.environ.get("JOOBLE_KEY"))
ann, targets = ats_targets(cfg, store)
runs = store.last_runs(2)
last = runs[0] if runs else None
new_run = last["id"] if (last and len(runs) > 1) else None
for f in ("updating", "discovering", "checking"):
    st.session_state.setdefault(f, False)
busy = st.session_state.updating or st.session_state.discovering or st.session_state.checking

# ------------------------------------------------------------------ en-tête
st.html(ui.hero(
    cand.get("nom", ""),
    f"Conformité · LCB-FT · KYC · sanctions · business analyst conformité · analyste crédit débutant — "
    f"juniors 0 à {EXP_MAX} ans — France uniquement — CDI ou CDD / intérim ≥ {DUR_MIN} mois — "
    f"salaire ≥ {SAL_MIN // 1000} k€ — publiées depuis moins de {cand.get('fraicheur_jours', 30)} jours",
    fmt_dt(last["finished"]) if last else "jamais",
    [("✅ " if ft_ok else "❌ ") + "France Travail", ("✅ " if gg_ok else "⚪ ") + "Google Emploi",
     ("✅ " if jb_ok else "⚪ ") + "Jooble", ("✅ " if az_ok else "⚪ ") + "Adzuna",
     f"🏦 {len(ann.employers)} employeurs suivis", f"🔌 {len(targets)} sites carrières lus directement"]))

bcol, mcol = st.columns([1, 2.4], vertical_alignment="center")
with bcol:
    st.button("🔄  Mettre à jour les offres", key="maj", width="stretch", disabled=busy,
              on_click=lambda: st.session_state.update(updating=True))
with mcol:
    _off = [n for n, ok in (("France Travail", ft_ok), ("Google Emploi", gg_ok), ("Jooble", jb_ok), ("Adzuna", az_ok)) if not ok]
    if len(_off) == 4:
        st.html(ui.notice("warn", "Aucune clé de plateforme : seuls les sites carrières lisibles directement sont lus. Ajoutez au moins "
                                  "Google Emploi (SERPAPI_KEY : LinkedIn, Indeed, WTTJ, HelloWork…) et France Travail — voir l'onglet Aide."))
    elif _off:
        st.html(ui.notice("info", "Sources non branchées : " + ", ".join(_off) + ". Chaque clé ajoutée élargit la recherche "
                                  "(onglet Aide, 5 minutes chacune, gratuites)."))

if st.session_state.updating:
    run_long("updating", "Mise à jour en cours… ne fermez pas la page", lambda p: run_update(cfg, store, progress=p))
if st.session_state.discovering:
    def _disc(p):
        found = discover(new_http(0.2), ann.employers, p)
        store.save_tokens(found)
        return found
    run_long("discovering", "Recherche des sites carrières lisibles (1 à 3 minutes)…", _disc)
if st.session_state.checking:
    def _check(p):
        res = check_links(new_http(0.1), sorted({e.site for e in ann.employers if e.site}), p)
        store.save_links(res)
        return res
    run_long("checking", "Vérification des liens de l'annuaire…", _check)

if "flash_error" in st.session_state:
    st.html(ui.notice("warn", "Problème : " + st.session_state.pop("flash_error")))
if "updating_result" in st.session_state:
    rep = st.session_state.pop("updating_result")
    errs = [s for s in rep["per_source"] if s["status"] == "erreur"]
    st.html(ui.notice("warn" if errs else "ok",
                      f"Mise à jour terminée : {rep['kept']} offres retenues sur {rep['fetched']} lues · "
                      f"{rep['duplicates_removed']} doublons fusionnés · {rep['expired']} offres retirées."
                      + (f" ⚠️ {len(errs)} source(s) en erreur : voir « Sources & diagnostic »." if errs else "")))
if "discovering_result" in st.session_state:
    found = st.session_state.pop("discovering_result")
    st.html(ui.notice("ok", f"{len(found)} site(s) carrières lisible(s) trouvé(s). Lancez « Mettre à jour les offres » pour les lire."))
if "checking_result" in st.session_state:
    res = st.session_state.pop("checking_result")
    bad = sum(1 for ok, _ in res.values() if not ok)
    st.html(ui.notice("warn" if bad else "ok", f"{len(res)} liens vérifiés · {bad} à revoir (voir l'onglet Employeurs)."))

# ------------------------------------------------------------------ filtres
rows = store.list()
fam_names = list(FAMILIES.values())
with st.sidebar:
    st.header("Filtres")
    min_score = st.slider("Score minimum", 0, 100, int(cand.get("score_minimum", 40)))
    fams = st.multiselect("Métier", fam_names, placeholder="Tous")
    sal_min = st.number_input("Salaire annuel minimum (€)", min_value=SAL_MIN, value=SAL_MIN, step=1000,
                              help=f"Les offres sous {SAL_MIN // 1000} k€ sont déjà écartées à la mise à jour.")
    with_unknown_sal = st.checkbox("Inclure les offres sans salaire indiqué", value=True,
                                   help="La plupart des offres n'affichent pas de salaire.")
    contrats = st.multiselect("Contrat", CONTRACTS, placeholder="CDI, CDD, intérim")
    only_junior = st.checkbox("Seulement « débutant / junior » explicite")
    max_age = st.slider("Publiée depuis (jours)", 1, int(cand.get("fraicheur_jours", 30)), int(cand.get("fraicheur_jours", 30)))
    cats = st.multiselect("Type d'employeur", CATEGORIES, placeholder="Tous")
    regions = st.multiselect("Région", REGION_NAMES + [NO_REGION], placeholder="Toute la France")
    sources = st.multiselect("Source", list(SOURCE_NAMES.values()), placeholder="Toutes")
    statuts = st.multiselect("Statut de candidature", STATUSES, default=[s for s in STATUSES if s not in ("Refusé", "Ignorée")])
    only_new = st.checkbox("Seulement les nouvelles depuis la dernière mise à jour")
    query = st.text_input("Recherche (intitulé ou employeur)")
    st.caption("Critères de collecte (mots-clés, expérience, salaire, durée) : config/profil.toml")

flt = []
for r in rows:
    a = age_days(r["posted_at"])
    if r["score"] < min_score or (a is not None and a > max_age) or r["status"] not in statuts:
        continue
    if fams and FAMILIES.get(r["family"]) not in fams:
        continue
    if r["salary_max"] and r["salary_max"] < sal_min:
        continue
    if not r["salary_max"] and not with_unknown_sal:
        continue
    if contrats and (r["contract"] or "Non précisé") not in contrats:
        continue
    if only_junior and r["exp_min"] != 0:
        continue
    if cats and (r["category"] or "Autre") not in cats:
        continue
    if regions and (r["region"] or NO_REGION) not in regions:
        continue
    if sources and SOURCE_NAMES.get(r["source"]) not in sources:
        continue
    if only_new and r["first_run"] != new_run:
        continue
    if query and query.lower() not in f"{r['title']} {r['company']}".lower():
        continue
    flt.append(r)

tab_offres, tab_emp, tab_manuel, tab_diag, tab_aide = st.tabs(
    ["📋 Offres", "🏦 Employeurs & sites carrières", "🔗 Recherches manuelles", "🩺 Sources & diagnostic", "ℹ️ Aide"])

# ------------------------------------------------------------------ offres
with tab_offres:
    st.html(ui.kpis([("Offres affichées", len(flt), "#2A9D8F"),
                     ("Nouvelles", sum(1 for r in rows if new_run and r["first_run"] == new_run), "#ff7a45"),
                     ("Conformité / KYC", sum(1 for r in flt if r["family"] == "conformite"), ui.FAM_COLORS["conformite"]),
                     ("Business analyst", sum(1 for r in flt if r["family"] == "ba"), ui.FAM_COLORS["ba"]),
                     ("Analyste crédit", sum(1 for r in flt if r["family"] == "credit"), ui.FAM_COLORS["credit"]),
                     ("Avec salaire", sum(1 for r in flt if r["salary_max"]), "#16a34a"),
                     ("Postulées", sum(1 for r in rows if r["status"] == "Postulé"), "#7C3AED")]))
    if not rows:
        st.html(ui.empty_state("Aucune offre pour l'instant", "Cliquez sur « Mettre à jour les offres ». "
                               "L'onglet « Sources & diagnostic » explique ce qui manque si rien ne remonte."))
    elif not flt:
        st.html(ui.empty_state("Aucune offre ne correspond aux filtres", "Baissez le score minimum ou élargissez les filtres."))
    else:
        t1, t2 = st.columns([2, 1])
        order = t1.segmented_control("Trier par", ["Pertinence", "Plus récentes", "Salaire"], default="Pertinence", key="order") or "Pertinence"
        t2.download_button("⬇️ Exporter (CSV)", pd.DataFrame([{
            "score": r["score"], "métier": FAMILIES.get(r["family"], r["family"]), "intitulé": r["title"], "employeur": r["company"],
            "type": r["category"], "lieu": r["location"], "région": r["region"], "contrat": ui.contract_label(r),
            "salaire": ui.salary_label(r), "expérience": r["experience"], "publiée": r["posted_at"], "statut": r["status"],
            "lien candidature": r["apply_url"]} for r in flt]).to_csv(index=False, sep=";").encode("utf-8-sig"),
            "offres_conformite.csv", "text/csv", width="stretch")
        if order == "Plus récentes":
            flt = sorted(flt, key=lambda r: r["posted_at"] or "", reverse=True)
        elif order == "Salaire":
            flt = sorted(flt, key=lambda r: (r["salary_max"] or 0, r["score"]), reverse=True)
        limit = st.session_state.get("limit", PAGE)
        shown = flt[:limit]
        for i in range(0, len(shown), 2):
            cols = st.columns(2, gap="medium")
            for j, col in enumerate(cols):
                if i + j >= len(shown):
                    continue
                r, n = shown[i + j], i + j
                with col, st.container(key=f"card_{n}"):
                    st.html(ui.offer_card(r, bool(new_run and r["first_run"] == new_run), age_text(r["posted_at"]),
                                          SOURCE_NAMES.get(r["source"], r["source"])))
                    a, b, c = st.columns([1.15, 1, 1.35], vertical_alignment="bottom")
                    a.link_button("Candidater ↗", ui.safe_url(r["apply_url"] or r["url"]), type="primary", width="stretch")
                    if b.button("Détails", key=f"det_{n}", width="stretch"):
                        detail_dialog(r["uid"])
                    sk = f"stat_{r['uid']}"
                    st.session_state[sk] = r["status"] if r["status"] in STATUSES else STATUSES[0]
                    c.selectbox("Statut", STATUSES, key=sk, label_visibility="collapsed", on_change=set_status, args=(r["uid"], sk))
        if len(flt) > limit and st.button(f"Afficher plus ({len(flt) - limit} restantes)", width="stretch"):
            st.session_state["limit"] = limit + PAGE
            st.rerun()

# ------------------------------------------------------------------ employeurs
with tab_emp:
    st.markdown(f"**{len(ann.employers)} employeurs** : banques françaises et étrangères, fintech et établissements de paiement, "
                "crypto, transfert d'argent (corridors Afrique / Caraïbes), RegTech, cabinets, assurances, gestionnaires d'actifs, "
                "régulateurs, cabinets de recrutement. Leurs offres arrivent de trois façons : **site carrières lu directement** (🔌), "
                "**France Travail / Adzuna**, ou **liens directs** à ouvrir vous-même. Seules les offres situées en France sont gardées.")
    tokens = store.tokens()
    links = store.links()
    counts = {}
    for r in rows:
        emp = r.get("employeur") or r["extra"].get("employeur")
        if emp:
            counts[emp] = counts.get(emp, 0) + 1
    e1, e2 = st.columns([1, 2])
    ecat = e1.multiselect("Type", CATEGORIES, placeholder="Tous", key="ecat")
    eq = e2.text_input("Chercher un employeur", key="eq")
    table = []
    for e in ann.employers:
        if (ecat and e.categorie not in ecat) or (eq and eq.lower() not in (e.nom + " " + " ".join(e.alias)).lower()):
            continue
        ats, tok = (e.ats, e.token) if e.token else (tokens.get(e.nom, {}).get("ats", ""), tokens.get(e.nom, {}).get("token", ""))
        lk = links.get(e.site) if e.site else None
        sl = e.search_links()
        table.append({"Employeur": e.nom + (" ✚" if e.ajoute else ""), "Type": e.categorie, "Offres retenues": counts.get(e.nom, 0),
                      "Site carrières": e.site or "",
                      "Lien": "—" if not e.site else ("non vérifié" if not lk else "✅ ok" if lk["ok"] else f"⚠️ {lk['code']}"),
                      "Lecture auto": f"🔌 {ats}" if tok else "—",
                      "Page lue": PUBLIC_PAGE[ats].format(t=tok) if tok and ats in PUBLIC_PAGE else "",
                      "Google": sl["Google"], "LinkedIn": sl["LinkedIn"], "WTTJ": sl["WTTJ"]})
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch", height=520, column_config={
        "Site carrières": st.column_config.LinkColumn(display_text="Ouvrir ↗"),
        "Page lue": st.column_config.LinkColumn(display_text="Offres ↗"),
        "Google": st.column_config.LinkColumn(display_text="Rechercher ↗"),
        "LinkedIn": st.column_config.LinkColumn(display_text="LinkedIn ↗"),
        "WTTJ": st.column_config.LinkColumn(display_text="WTTJ ↗"),
        "Offres retenues": st.column_config.NumberColumn(format="%d")})
    st.caption("« Rechercher » ouvre une requête Google pré-remplie (employeur + conformité). ✚ = employeur ajouté par vous.")
    d1, d2 = st.columns(2)
    d1.button("🔎 Trouver les sites carrières lisibles automatiquement", width="stretch", disabled=busy,
              on_click=lambda: st.session_state.update(discovering=True),
              help="Teste, pour chaque employeur, les API publiques Greenhouse, Lever, Ashby, Workable, SmartRecruiters et Recruitee. "
                   "Un site n'est gardé que s'il publie au moins une offre en France.")
    d2.button("✅ Vérifier les liens de l'annuaire", width="stretch", disabled=busy,
              on_click=lambda: st.session_state.update(checking=True))
    if tokens:
        with st.expander(f"{len(tokens)} site(s) carrières trouvé(s) automatiquement"):
            st.dataframe(pd.DataFrame([{"Employeur": n, "Logiciel": t["ats"], "Jeton": t["token"], "Offres (toutes)": t["n"]}
                                       for n, t in tokens.items()]), hide_index=True, width="stretch")
            rmt = st.selectbox("Retirer un résultat erroné", list(tokens), key="rmt")
            if st.button("Retirer ce site", key="rmt_btn"):
                store.delete_token(rmt)
                st.rerun()

    st.subheader("Ajouter un employeur")
    extra = cfg.extra_employers()
    a1, a2 = st.columns(2)
    nom = a1.text_input("Nom", key="add_nom")
    cat = a2.selectbox("Type", CATEGORIES, key="add_cat")
    url = st.text_input("Adresse de sa page carrières (facultatif)", placeholder="https://careers.exemple.com", key="add_url")
    if st.button("Détecter le logiciel de recrutement") and url:
        try:
            st.session_state["found"] = detect_ats(Http(cfg.user_agent), url)
            if not st.session_state["found"]:
                st.info("Aucun logiciel lisible reconnu : l'employeur sera ajouté avec son lien, ses offres arriveront par France Travail / Adzuna.")
        except HttpError as exc:
            st.error(str(exc))
    found = st.session_state.get("found", [])
    choice = st.selectbox("Logiciel détecté", ["aucun"] + [f"{f['ats']}:{f['token']}" for f in found], key="add_ats") if found else "aucun"
    if st.button("➕ Ajouter à l'annuaire", type="primary", disabled=not nom):
        ats, tok = (choice.split(":", 1) if choice != "aucun" else ("", ""))
        extra.append({"nom": nom.strip(), "categorie": cat, "site": url.strip() if url.startswith("http") else "", "ats": ats, "token": tok})
        cfg.save_extra_employers(extra)
        st.session_state.pop("found", None)
        st.rerun()
    with st.expander("Ajouter à la main un jeton connu"):
        m1, m2, m3 = st.columns(3)
        mn, ma, mt = m1.text_input("Employeur", key="mn"), m2.selectbox("Logiciel", sorted(PARSERS), key="ma"), m3.text_input("Jeton", key="mt")
        if st.button("Ajouter", key="man_add") and mn and mt:
            extra.append({"nom": mn.strip(), "categorie": "Autre", "site": "", "ats": ma, "token": mt.strip()})
            cfg.save_extra_employers(extra)
            st.rerun()
    if extra:
        rm = st.selectbox("Retirer un employeur ajouté", [e["nom"] for e in extra], key="rm_extra")
        if st.button("Retirer", key="rm_extra_btn"):
            cfg.save_extra_employers([e for e in extra if e["nom"] != rm])
            st.rerun()

# ------------------------------------------------------------------ recherches manuelles
with tab_manuel:
    st.markdown("LinkedIn, Indeed, Welcome to the Jungle, APEC, HelloWork et Jobteaser **interdisent la collecte automatique** : "
                "Radar Emploi ne les lit pas. Voici des recherches pré-remplies (France, récentes, niveau débutant / junior quand "
                "le site le permet) que **vous** ouvrez.")
    m1, m2 = st.columns([2, 1])
    kw = m1.selectbox("Mot-clé", ["analyste LCB-FT junior", "analyste KYC junior", "chargé de conformité junior", "analyste sanctions",
                                  "compliance analyst", "business analyst KYC", "business analyst conformité",
                                  "analyste crédit junior", "analyste crédit débutant"] + cfg.recherche.get("mots_cles", []))
    lieu = m2.text_input("Lieu", "France")
    dl = deep_links(kw, lieu, 14)
    cols = st.columns(4)
    for i, (name, link) in enumerate(dl.items()):
        cols[i % 4].link_button(f"{name} ↗", link, width="stretch")

# ------------------------------------------------------------------ diagnostic
with tab_diag:
    st.subheader("Clés et accès")
    for name, ok, hint in [
        ("France Travail (API officielle)", ft_ok, "Source principale pour les banques et assureurs, partout en France : renseignez FT_CLIENT_ID et FT_CLIENT_SECRET (voir Aide)."),
        ("Google Emploi via SerpApi", gg_ok, "Couvre LinkedIn, Indeed, Welcome to the Jungle, HelloWork, APEC, Jobteaser et les sites des employeurs : clé SERPAPI_KEY (serpapi.com)."),
        ("Jooble (API officielle)", jb_ok, "Agrégateur gratuit : clé JOOBLE_KEY à demander sur jooble.org/api/about."),
        ("Adzuna (API officielle)", az_ok, "Agrège beaucoup de sites carrières de grands groupes. Clés gratuites sur developer.adzuna.com."),
        ("Sites carrières lus directement", bool(targets), "Cliquez sur « Trouver les sites carrières lisibles » dans l'onglet Employeurs.")]:
        st.markdown(f"{'✅' if ok else '❌'} **{name}** — {'prêt' if ok else hint}")
    st.caption(" · ".join(f"{k} : {'trouvée' if os.environ.get(k) else 'absente'}" for k in KEYS[:6]))
    if ft_ok:
        _id, _sec = os.environ["FT_CLIENT_ID"], os.environ["FT_CLIENT_SECRET"]
        _odd = [c for c in _id + _sec if not (c.isascii() and c.isprintable()) or c in "'\" "]
        st.caption(f"Identifiant lu : {_id[:8]}… ({len(_id)} caractères) · clé secrète lue : {len(_sec)} caractères"
                   + (f" · ⚠️ {len(_odd)} caractère(s) suspect(s) (guillemet, espace ou caractère invisible)" if _odd else ""))
        if st.button("🔌 Tester la connexion France Travail", key="ft_test"):
            try:
                from core.sources.france_travail import get_token
                get_token(Http(cfg.user_agent, retries=0))
                st.success("Connexion réussie : France Travail accepte vos clés et l'abonnement à l'API Offres d'emploi v2 est actif.")
            except HttpError as exc:
                st.error(str(exc))
    st.subheader("Dernière mise à jour")
    if not last:
        st.info("Aucune mise à jour effectuée pour l'instant.")
    else:
        rep = last["report"]
        st.caption(f"Terminée le {fmt_dt(last['finished'])} · {rep.get('fetched', 0)} offres lues · {rep.get('kept', 0)} retenues · "
                   f"{rep.get('duplicates_removed', 0)} doublons fusionnés")
        st.html(ui.source_tiles(rep.get("per_source", [])))
        warns = [(s["label"], w) for s in rep.get("per_source", []) for w in s["warnings"]]
        if warns:
            with st.expander(f"{len(warns)} avertissement(s)"):
                for n_, w in warns:
                    st.write(f"**{n_}** — {w}")
        if rep.get("rejected"):
            st.subheader("Pourquoi des offres ont été écartées")
            st.bar_chart(pd.Series(rep["rejected"], name="offres").sort_values(), horizontal=True)
    if rows:
        st.subheader("Répartition des offres retenues")
        g1, g2 = st.columns(2)
        g1.bar_chart(pd.Series([r["region"] or NO_REGION for r in rows]).value_counts(), horizontal=True)
        g2.bar_chart(pd.Series([FAMILIES.get(r["family"], r["family"]) for r in rows]).value_counts(), horizontal=True)

# ------------------------------------------------------------------ aide
with tab_aide:
    st.markdown(f"""
**Ce que fait le bouton « Mettre à jour ».** Il interroge, pour toute la France :
- **France Travail** (API officielle) ;
- **Google Emploi** via SerpApi : regroupe les offres de LinkedIn, Indeed, Welcome to the Jungle, HelloWork, APEC, Jobteaser,
  Glassdoor et des sites carrières des employeurs ;
- **Jooble** et **Adzuna** (agrégateurs, API officielles) ;
- les **sites carrières** des employeurs de l'annuaire lisibles par API publique.

Il ne garde ensuite que les offres qui remplissent **toutes** ces conditions :

- **en France** (métropole et outre-mer) : un lieu étranger, « Remote », « Europe » ou un lieu introuvable est écarté ;
- **métier** : conformité / LCB-FT / KYC / sanctions et embargos ; business analyst sur un sujet KYC, LCB-FT ou conformité ;
  analyste crédit **ouvert aux débutants** (au plus {cand.get('credit_experience_max_ans', 1)} an d'expérience demandé) ;
- **junior** : au plus {EXP_MAX} ans d'expérience demandés, pas d'intitulé senior, manager, responsable, head, lead… ;
- **contrat** : CDI, ou CDD / intérim d'au moins {DUR_MIN} mois (sans durée indiquée, l'offre est gardée et signalée) ;
  stages, alternances, VIE, freelance et saisonniers sont écartés ;
- **salaire** : une offre qui affiche moins de {SAL_MIN // 1000} k€ brut annuel est écartée ; sans salaire affiché, elle est gardée ;
- **récente** : publiée depuis moins de {cand.get('fraicheur_jours', 30)} jours.

Les doublons sont fusionnés (le lien direct de l'employeur est préféré) et chaque offre reçoit une note sur 100.
L'onglet « Sources & diagnostic » montre combien d'offres ont été écartées et pourquoi.

**Clés à renseigner** (dans `.env` en local, ou *Settings → Secrets* sur Streamlit Cloud, puis *Reboot app*) :

| Source | Clé(s) | Où l'obtenir |
|---|---|---|
| Google Emploi | `SERPAPI_KEY` | serpapi.com → compte gratuit → *Your Private API Key* (quota mensuel limité ; 6 recherches par mise à jour par défaut) |
| Jooble | `JOOBLE_KEY` | jooble.org/api/about → formulaire, clé envoyée par e-mail |
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | developer.adzuna.com → *Register* |
| France Travail | `FT_CLIENT_ID`, `FT_CLIENT_SECRET` | voir ci-dessous |

**Clés France Travail (gratuit).** francetravail.io → « Mes applications » → créer une application → l'abonner à l'API
**Offres d'emploi v2** → copier l'identifiant et la clé secrète :
- en local, dans le fichier `.env` à côté de `app.py` (`FT_CLIENT_ID=...` et `FT_CLIENT_SECRET=...`) ;
- sur Streamlit Cloud, dans *Settings → Secrets* (`FT_CLIENT_ID = "..."` et `FT_CLIENT_SECRET = "..."`), puis *Reboot app*.

**Les grandes banques et assureurs.** Leurs sites carrières n'offrent pas d'accès automatisé autorisé : leurs offres arrivent
par France Travail et Adzuna, et l'onglet Employeurs donne les liens directs.

**Ce que l'application ne fait pas.** Elle n'invente aucun lien, ne contourne aucune protection et ne lit pas directement LinkedIn,
Indeed, WTTJ, APEC, HelloWork ou Jobteaser : leurs offres arrivent par Google Emploi, et l'onglet « Recherches manuelles » donne
des recherches pré-remplies sur chacun.

**Personnaliser.** Mots-clés, expérience, salaire, durée minimale : `config/profil.toml`. Employeurs : `config/employeurs.csv` ou l'onglet Employeurs.
""")
