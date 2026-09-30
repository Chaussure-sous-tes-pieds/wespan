"""Intégration KDE : règle de fenêtre KWin, script KWin, fond d'écran Plasma, démarrage auto."""
import os
import re
import shutil
import subprocess
from pathlib import Path

from .settings import (CONFIG_DIR, KWIN_RULE_GROUP, KWIN_SCRIPT_ID, PLUGIN_ID, WINDOW_TITLE)

XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
KWINRULES = XDG_CONFIG / "kwinrulesrc"
AUTOSTART = XDG_CONFIG / "autostart" / "wespan.desktop"
AUTOSTART_TRAY = XDG_CONFIG / "autostart" / "wespan-tray.desktop"
LEGACY_TITLES = ("WE-fond-etendu", "WE-fond-principal", "WE-fond-vertical")


def _run(*cmd, timeout=15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def qdbus() -> str:
    return shutil.which("qdbus6") or shutil.which("qdbus-qt6") or shutil.which("qdbus") or "qdbus6"


def kwrite(file: str, group: str, key: str, value=None, delete=False) -> None:
    cmd = ["kwriteconfig6", "--file", file, "--group", group, "--key", key]
    cmd += ["--delete"] if delete else [str(value)]
    _run(*cmd)


def kwin_reconfigure() -> None:
    _run(qdbus(), "org.kde.KWin", "/KWin", "reconfigure")


# --- règle de fenêtre -----------------------------------------------------------------------

def _rule_groups() -> dict:
    """{groupe: {clé: valeur}} de kwinrulesrc."""
    groups, cur = {}, None
    try:
        for line in KWINRULES.read_text().splitlines():
            if m := re.match(r"^\[(.+)\]$", line):
                cur = groups.setdefault(m.group(1), {})
            elif cur is not None and "=" in line:
                k, v = line.split("=", 1)
                cur[k] = v
    except OSError:
        pass
    return groups


def rule_ok(w: int, h: int) -> bool:
    g = _rule_groups()
    r = g.get(KWIN_RULE_GROUP, {})
    rules = g.get("General", {}).get("rules", "").split(",")
    return KWIN_RULE_GROUP in rules and r.get("title") == WINDOW_TITLE and r.get("titlematch") == "2" \
        and r.get("size") == f"{w},{h}" and r.get("sizerule") == "2"


def rule_size() -> tuple | None:
    try:
        w, h = _rule_groups().get(KWIN_RULE_GROUP, {}).get("size", "").split(",")
        return int(w), int(h)
    except ValueError:
        return None


def ensure_rule(w: int, h: int) -> None:
    """Fenêtre créée directement à la bonne taille (sinon KWin la réduit à un écran), sans bordure,
    hors barre des tâches/pager/Alt+Tab, sans focus, sur tous les bureaux."""
    groups = _rule_groups()
    rules = [r for r in groups.get("General", {}).get("rules", "").split(",") if r]
    # retire les règles des versions précédentes
    for name, keys in groups.items():
        if keys.get("title") in LEGACY_TITLES:
            _delete_group(name)
            rules = [r for r in rules if r != name]
    g = KWIN_RULE_GROUP
    values = {
        "Description": "WE Span - fenêtre cachée de Wallpaper Engine",
        "title": WINDOW_TITLE, "titlematch": 2,          # sous-chaîne : wespan-canvas-a / -b
        "size": f"{w},{h}", "sizerule": 2,
        "noborder": "true", "noborderrule": 2,
        "skiptaskbar": "true", "skiptaskbarrule": 2,
        "skippager": "true", "skippagerrule": 2,
        "skipswitcher": "true", "skipswitcherrule": 2,
        "acceptfocus": "false", "acceptfocusrule": 2,
        "desktops": "", "desktopsrule": 2,
    }
    for k, v in values.items():
        kwrite("kwinrulesrc", g, k, v)
    if g not in rules:
        rules.append(g)
    kwrite("kwinrulesrc", "General", "rules", ",".join(rules))
    kwrite("kwinrulesrc", "General", "count", len(rules))
    kwin_reconfigure()


def _delete_group(name: str) -> None:
    try:
        text = KWINRULES.read_text()
    except OSError:
        return
    text = re.sub(r"\[" + re.escape(name) + r"\]\n(?:[^\[\n][^\n]*\n|\n)*", "", text)
    KWINRULES.write_text(text)


def remove_rule() -> None:
    groups = _rule_groups()
    rules = [r for r in groups.get("General", {}).get("rules", "").split(",") if r and r != KWIN_RULE_GROUP]
    _delete_group(KWIN_RULE_GROUP)
    kwrite("kwinrulesrc", "General", "rules", ",".join(rules))
    kwrite("kwinrulesrc", "General", "count", len(rules))
    kwin_reconfigure()


# --- script KWin ----------------------------------------------------------------------------

def x_screen_size() -> tuple | None:
    """Taille actuelle de l'écran Xwayland (celui que voit Wine), ou None si inconnue."""
    m = re.search(r"current (\d+) x (\d+)", _run("xrandr", "--current", timeout=5))
    return (int(m[1]), int(m[2])) if m else None


def kwin_script_installed() -> bool:
    return any((Path(d) / "kwin/scripts" / KWIN_SCRIPT_ID / "metadata.json").exists()
               for d in [Path.home() / ".local/share", Path("/usr/share")])


def kwin_script_enabled() -> bool:
    return _run("kreadconfig6", "--file", "kwinrc", "--group", "Plugins", "--key", f"{KWIN_SCRIPT_ID}Enabled") == "true"


def kwin_script_loaded() -> bool:
    return _run(qdbus(), "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.isScriptLoaded", KWIN_SCRIPT_ID) == "true"


def enable_kwin_script(on: bool = True) -> None:
    kwrite("kwinrc", "Plugins", f"{KWIN_SCRIPT_ID}Enabled", "true" if on else "false")
    # décharger d'abord : après une mise à jour, KWin garderait l'ancienne version en mémoire
    _run(qdbus(), "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", KWIN_SCRIPT_ID)
    kwin_reconfigure()
    if on:
        _run(qdbus(), "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.start")


def install_package(kind: str, src: Path) -> bool:
    """kind : 'KWin/Script' ou 'Plasma/Wallpaper' (installation utilisateur)."""
    out = subprocess.run(["kpackagetool6", "--type", kind, "--upgrade", str(src)], capture_output=True, text=True)
    if out.returncode != 0:
        out = subprocess.run(["kpackagetool6", "--type", kind, "--install", str(src)], capture_output=True, text=True)
    return out.returncode == 0


# --- fond d'écran Plasma --------------------------------------------------------------------

def plasma_eval(js: str) -> str:
    return _run(qdbus(), "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", js)


def plasma_plugins() -> list[str]:
    out = plasma_eval('var r=[]; for (const d of desktops()) r.push(d.wallpaperPlugin); print(r.join(","));')
    return [p for p in out.split(",") if p]


def plasma_active() -> bool:
    p = plasma_plugins()
    return bool(p) and all(x == PLUGIN_ID for x in p)


def apply_plasma(on: bool = True, fallback: str = "org.kde.image", reload: bool = False) -> None:
    plugin = PLUGIN_ID if on else fallback
    if on and reload:   # force Plasma à relire le QML du fond d'écran (mise à jour)
        plasma_eval('for (const d of desktops()) { d.wallpaperPlugin = "org.kde.color"; }')
    plasma_eval(f'for (const d of desktops()) {{ d.wallpaperPlugin = "{plugin}"; }}')


def plugin_installed() -> bool:
    return any((Path(d) / "plasma/wallpapers" / PLUGIN_ID / "metadata.json").exists()
               for d in [Path.home() / ".local/share", Path("/usr/share")])


# --- démarrage automatique ------------------------------------------------------------------

def autostart_enabled() -> bool:
    try:
        text = AUTOSTART.read_text()
    except OSError:
        return False
    return "Hidden=true" not in text


def set_autostart(on: bool, exe: str) -> None:
    AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=WE Span\n"
        "Comment=Wallpaper Engine as a Plasma wallpaper\n"
        f"Exec={exe} daemon\n"
        "Icon=wespan\n"
        "X-KDE-autostart-phase=2\n"
        + ("" if on else "Hidden=true\n"))


def tray_autostart_enabled() -> bool:
    try:
        return "Hidden=true" not in AUTOSTART_TRAY.read_text()
    except OSError:
        return False


def set_tray_autostart(on: bool, exe: str) -> None:
    AUTOSTART_TRAY.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART_TRAY.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=WE Span (tray)\n"
        "Comment=WE Span icon in the system tray\n"
        f"Exec={exe} settings --tray\n"
        "Icon=wespan\n"
        "X-KDE-autostart-phase=2\n"
        + ("" if on else "Hidden=true\n"))
