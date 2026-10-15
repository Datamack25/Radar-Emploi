"""Chargement de config/profil.toml et des employeurs ajoutés depuis l'interface."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"


@dataclass
class Config:
    profil: dict

    @property
    def candidat(self) -> dict:
        return self.profil.get("candidat", {})

    @property
    def recherche(self) -> dict:
        return self.profil.get("recherche", {})

    @property
    def db_path(self) -> Path:
        DATA.mkdir(exist_ok=True)
        return DATA / "radar3.db"

    @property
    def employeurs_csv(self) -> Path:
        return CONFIG / "employeurs.csv"

    @property
    def user_agent(self) -> str:
        contact = os.environ.get("RADAR_CONTACT", "").strip()
        return "RadarEmploi/3.0 (veille personnelle d'offres d'emploi" + (f"; contact: {contact}" if contact else "") + ")"

    def extra_employers(self) -> list[dict]:
        p = DATA / "employeurs_ajoutes.json"
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        except (OSError, ValueError):
            return []

    def save_extra_employers(self, lst: list[dict]) -> None:
        DATA.mkdir(exist_ok=True)
        (DATA / "employeurs_ajoutes.json").write_text(json.dumps(lst, ensure_ascii=False, indent=1), encoding="utf-8")


def load_config() -> Config:
    with open(CONFIG / "profil.toml", "rb") as f:
        return Config(tomllib.load(f))
