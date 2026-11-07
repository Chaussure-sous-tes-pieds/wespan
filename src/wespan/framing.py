"""Cadrage d'un fond : remplir / ajuster / étirer, zoom et position, réglables par fond.

Wallpaper Engine remplit toujours sa fenêtre en rognant la scène au centre, quelle que soit la
forme de la fenêtre. Pour pouvoir montrer le fond entier (ajuster, étirer, dézoomer), on lui fait
donc rendre la scène dans une fenêtre aux proportions d'origine de la scène, et c'est le fond
Plasma qui place et met à l'échelle l'image (voir main.qml). Sans réglage, rien ne change : la
fenêtre couvre tous les écrans, comme avant (image la plus nette).
"""
import json
import shutil
import struct
import subprocess
from pathlib import Path

FITS = ("fill", "fit", "stretch")
DEFAULT = {"fit": "fill", "zoom": 100, "x": 0, "y": 0}
ZOOM_MIN, ZOOM_MAX = 25, 400

_cache: dict = {}


def normalize(v) -> dict:
    """Réglage complet et borné (les clés manquantes ou fausses prennent la valeur par défaut)."""
    out = dict(DEFAULT)
    if not isinstance(v, dict):
        return out
    if v.get("fit") in FITS:
        out["fit"] = v["fit"]
    for k, lo, hi in (("zoom", ZOOM_MIN, ZOOM_MAX), ("x", -100, 100), ("y", -100, 100)):
        try:
            out[k] = int(max(lo, min(hi, round(float(v.get(k, out[k]))))))
        except (TypeError, ValueError):
            pass
    return out


def is_default(v) -> bool:
    return normalize(v) == DEFAULT


def needs_native(v) -> bool:
    """Ce cadrage demande-t-il l'image entière du fond (pas seulement la partie que WE garde
    en remplissant la fenêtre) ?"""
    v = normalize(v)
    return v["fit"] != "fill" or v["zoom"] < 100


def fit_inside(nw: int, nh: int, bw: int, bh: int) -> tuple[int, int]:
    """Plus grand rectangle aux proportions nw:nh qui tient dans bw×bh (dimensions paires)."""
    if nw <= 0 or nh <= 0 or bw <= 0 or bh <= 0:
        return bw, bh
    k = min(bw / nw, bh / nh)
    w, h = int(nw * k) // 2 * 2, int(nh * k) // 2 * 2
    return max(2, min(w, bw)), max(2, min(h, bh))


# --- taille d'origine du fond ------------------------------------------------------------------

def _pkg_file(pkg: Path, name: str) -> bytes | None:
    """Un fichier d'une archive scene.pkg de Wallpaper Engine (« PKGV00xx » : en-tête, table
    des fichiers nom/position/longueur, puis les données)."""
    with open(pkg, "rb") as f:
        head = f.read(4 << 20)          # l'en-tête et scene.json sont au début
        def u32(o):
            return struct.unpack_from("<I", head, o)[0]
        o = 4 + u32(0)                  # version
        count = u32(o); o += 4
        entries = []
        for _ in range(min(count, 100000)):
            n = u32(o); o += 4
            fname = head[o:o + n].decode("utf-8", "replace"); o += n
            entries.append((fname, u32(o), u32(o + 4))); o += 8
        for fname, off, length in entries:
            if fname == name:
                if length > 16 << 20:
                    return None
                f.seek(o + off)
                return f.read(length)
    return None


def _scene_size(folder: Path, project: dict) -> tuple[int, int] | None:
    raw = None
    scene = str(project.get("file") or "scene.json")
    if (folder / scene).is_file():
        raw = (folder / scene).read_bytes()
    elif (folder / "scene.pkg").is_file():
        raw = _pkg_file(folder / "scene.pkg", scene)
    if not raw:
        return None
    proj = (json.loads(raw.decode("utf-8-sig")).get("general") or {}).get("orthogonalprojection") or {}
    w, h = int(proj.get("width") or 0), int(proj.get("height") or 0)
    return (w, h) if w > 0 and h > 0 else None


def _video_size(f: Path) -> tuple[int, int] | None:
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation", "-of", "json", str(f)],
                         capture_output=True, text=True, timeout=20).stdout
    st = (json.loads(out).get("streams") or [{}])[0]
    w, h = int(st.get("width") or 0), int(st.get("height") or 0)
    rot = 0
    for sd in st.get("side_data_list") or []:
        rot = int(sd.get("rotation") or 0)
    if rot % 180:
        w, h = h, w
    return (w, h) if w > 0 and h > 0 else None


def native_size(project_json: Path | None) -> tuple[int, int] | None:
    """Taille d'origine (proportions) d'un fond scène ou vidéo ; None si inconnue (page web,
    application, fichier illisible). Mise en cache tant que project.json ne change pas."""
    if not project_json:
        return None
    pj = Path(project_json)
    try:
        key = (str(pj), pj.stat().st_mtime_ns)
    except OSError:
        return None
    if key in _cache:
        return _cache[key]
    size = None
    try:
        p = json.loads(pj.read_text(encoding="utf-8-sig"))
        kind = str(p.get("type") or "").lower()
        if kind == "scene":
            size = _scene_size(pj.parent, p)
        elif kind == "video" and p.get("file"):
            size = _video_size(pj.parent / str(p["file"]))
    except (OSError, ValueError, KeyError, struct.error, subprocess.SubprocessError, TypeError):
        size = None
    _cache[key] = size
    return size
