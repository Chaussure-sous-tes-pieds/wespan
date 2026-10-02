"""Réglages personnalisables d'un fond (project.json → general.properties), comme dans Wallpaper Engine.

Types gérés : bool, slider, color (« r g b » de 0 à 1), combo, textinput ; group et text servent de
titres / textes d'information. Les conditions (« clock.value==true && style.value==1 ») masquent les
réglages qui ne s'appliquent pas.
"""
import html
import json
import re
from pathlib import Path

EDITABLE = ("bool", "slider", "color", "combo", "textinput")
SHOWN = EDITABLE + ("group", "text")

# libellés intégrés à Wallpaper Engine (clés « ui_… »)
BUILTIN = {
    "ui_browse_properties_scheme_color": ("Couleur du thème", "Scheme color"),
    "ui_browse_properties_alignment": ("Alignement", "Alignment"),
    "ui_browse_properties_rate": ("Vitesse de lecture", "Playback rate"),
    "ui_browse_properties_volume": ("Volume", "Volume"),
}


def _label(text, loc: dict, lang: str) -> str:
    text = str(text or "")
    if text in loc:
        text = str(loc[text])
    elif text in BUILTIN:
        text = BUILTIN[text][0 if lang == "fr" else 1]
    elif text.startswith("ui_"):
        text = text.rsplit("_properties_", 1)[-1].replace("_", " ").strip().capitalize()
    text = re.sub(r"<br\s*/?>|<hr\s*/?>|</p>|</div>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _localization(general: dict, lang: str) -> dict:
    loc = general.get("localization") or {}
    if not isinstance(loc, dict):
        return {}
    for code in ([f"{lang}-{lang}", lang] if lang else []) + ["en-us", "en"]:
        for k, v in loc.items():
            if k.lower() == code and isinstance(v, dict):
                return v
    return {}


def condition_ok(cond: str, values: dict) -> bool:
    """Évalue une condition de Wallpaper Engine (syntaxe JavaScript simple). En cas de doute : vrai."""
    if not cond or not str(cond).strip():
        return True
    expr = str(cond)
    expr = re.sub(r"([A-Za-z_]\w*)\.value", lambda m: repr(values.get(m[1])), expr)
    expr = expr.replace("&&", " and ").replace("||", " or ").replace("===", "==").replace("!==", "!=")
    expr = re.sub(r"!(?!=)", " not ", expr)
    expr = re.sub(r"\btrue\b", "True", expr)
    expr = re.sub(r"\bfalse\b", "False", expr)
    if re.search(r"[A-Za-z_]\w*\s*\(|__|\[|lambda|import", expr):
        return True
    try:
        return bool(eval(expr, {"__builtins__": {}}, {}))   # noqa: S307 - expression filtrée ci-dessus
    except Exception:  # noqa: BLE001
        return True


def _norm(v, ty):
    """Valeur comparable dans les conditions (WE compare souvent des combos à des nombres)."""
    if ty == "combo":
        try:
            f = float(v)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return v
    return v


def load(project_json: Path, overrides: dict | None = None, lang: str = "en") -> list[dict]:
    """Liste ordonnée des réglages, avec leur valeur actuelle (personnalisée sinon d'origine)."""
    try:
        p = json.loads(Path(project_json).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    general = p.get("general") or {}
    loc = _localization(general, lang)
    overrides = overrides or {}
    raw = general.get("properties") or {}
    items = []
    for key, v in raw.items():
        if not isinstance(v, dict) or v.get("type") not in SHOWN:
            continue
        ty = v["type"]
        value = overrides.get(key, v.get("value"))
        it = {
            "key": key, "type": ty, "order": v.get("order", 0) if isinstance(v.get("order"), (int, float)) else 0,
            "label": _label(v.get("text") or key, loc, lang), "value": value, "default": v.get("value"),
            "custom": key in overrides and overrides[key] != v.get("value"),
            "condition": v.get("condition") or "",
        }
        if ty == "slider":
            it.update({"min": float(v.get("min", 0)), "max": float(v.get("max", 100)),
                       "step": float(v.get("step") or 0) or (1.0 if v.get("precision", 0) == 0 else 0.01),
                       "precision": int(v.get("precision") or 0)})
        elif ty == "combo":
            it["options"] = [{"label": _label(o.get("label", o.get("value")), loc, lang), "value": o.get("value")}
                             for o in v.get("options") or [] if isinstance(o, dict)]
        elif ty == "color":
            it["value"] = str(value or "1 1 1")
        items.append(it)
    items.sort(key=lambda i: i["order"])
    values = {i["key"]: _norm(i["value"], i["type"]) for i in items}
    for i in items:
        i["visible"] = condition_ok(i["condition"], values)
    # un texte « titre » sans réglage visible derrière lui ne sert à rien
    return [i for i in items if i["label"] or i["type"] in EDITABLE]


def color_to_hex(v: str) -> str:
    try:
        r, g, b = (max(0.0, min(1.0, float(x))) for x in str(v).split()[:3])
    except ValueError:
        return "#ffffff"
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def hex_to_color(h: str) -> str:
    h = h.lstrip("#")[-6:]
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return "1 1 1"
    return f"{r:.5f} {g:.5f} {b:.5f}"
