"""Languages.

English and French are built in: every string of the app is written as t("français", "English").
Any other language is a JSON file i18n/<code>.json mapping the English text to its translation:

    {"_name": "Deutsch", "Wallpapers": "Hintergründe", ...}

Missing entries fall back to English. i18n/_template.json lists the strings to translate; regenerate it
with `wespan i18n-template src/wespan/i18n/_template.json`.
"""
import json
import os
from pathlib import Path

DIR = Path(__file__).parent / "i18n"
BUILTIN = {"en": "English", "fr": "Français"}


def catalogs() -> dict:
    """{code: {english: translation}} for the extra languages shipped in i18n/."""
    out = {}
    for f in sorted(DIR.glob("[!_]*.json")) if DIR.is_dir() else []:
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return out


def languages() -> list[dict]:
    langs = [{"code": c, "name": n} for c, n in BUILTIN.items()]
    for code, cat in catalogs().items():
        if code not in BUILTIN:
            langs.append({"code": code, "name": cat.get("_name", code)})
    return langs


def resolve(choice: str) -> str:
    """Effective language code for a setting value ("auto" or a code)."""
    codes = [l["code"] for l in languages()]
    env = os.environ.get("WESPAN_LANG")
    if env == "_template":
        return env
    if choice in codes:
        return choice
    if env in codes:
        return env
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG", "LC_TIME", "LC_ADDRESS"):
        val = os.environ.get(var, "").lower()
        for part in val.split(":"):
            code = part.split("_")[0].split(".")[0]
            if code in codes and code != "en":
                return code
    return "en"
