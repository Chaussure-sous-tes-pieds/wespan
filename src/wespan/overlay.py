"""Réglages personnalisés d'un fond : dossier « superposé » que Wallpaper Engine ouvre à la place.

En mode fenêtre (-playInWindow), WE ignore « -control applyProperties » comme ses réglages
enregistrés (config.json → wproperties). Il lit en revanche les valeurs par défaut du project.json
qu'on lui donne. On prépare donc, dans le dossier de WE (lecteur S:, comme les fonds eux-mêmes),
projects/wespan-custom/<id>/ : des liens vers tous les fichiers du fond (rien n'est copié) et un
project.json dont les valeurs par défaut sont les vôtres.
"""
import json
import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger("wespan.overlay")

DIR_NAME = "wespan-custom"


def root(info) -> Path | None:
    return info.we_dir / "projects" / DIR_NAME if info.we_dir else None


def build(info, project_json: Path, wid: str, props: dict) -> Path:
    """Chemin du project.json à ouvrir : l'original sans réglage personnalisé, sinon la superposition."""
    base = root(info)
    if not props or not base:
        return project_json
    src = Path(project_json).parent
    dst = base / wid
    try:
        p = json.loads(Path(project_json).read_text(encoding="utf-8-sig"))
        known = (p.get("general") or {}).get("properties") or {}
        applied = 0
        for k, v in props.items():
            if isinstance(known.get(k), dict):
                known[k]["value"] = v
                applied += 1
        if not applied:
            return project_json
        dst.mkdir(parents=True, exist_ok=True)
        wanted = {f.name for f in src.iterdir() if f.name != "project.json"}
        for f in dst.iterdir():              # liens d'une ancienne version du fond
            if f.name != "project.json" and (f.name not in wanted or not f.is_symlink()
                                             or Path(os.readlink(f)) != src / f.name):
                f.unlink() if f.is_symlink() or f.is_file() else shutil.rmtree(f)
        for name in wanted:
            if not (dst / name).exists():
                os.symlink(src / name, dst / name)
        tmp = dst / "project.json.tmp"
        tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(dst / "project.json")
        return dst / "project.json"
    except (OSError, ValueError) as e:
        log.warning("custom settings for %s not applied: %s", wid, e)
        return project_json


def remove(info, wid: str) -> None:
    base = root(info)
    if base and (base / wid).is_dir():
        shutil.rmtree(base / wid, ignore_errors=True)
