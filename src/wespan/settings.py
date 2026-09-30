"""Réglages persistants (~/.config/wespan/settings.json) et chemins d'exécution."""
import json
import os
from pathlib import Path

APP_ID = "wespan"
DBUS_NAME = "org.wespan.Daemon"
DBUS_PATH = "/Daemon"
DBUS_IFACE = "org.wespan.Daemon"
WINDOW_TITLE = "wespan-canvas"       # titre de la fenêtre cachée de Wallpaper Engine
WE_APPID = "431960"
PLUGIN_ID = "org.wespan.wallpaper"
KWIN_SCRIPT_ID = "wespan"
KWIN_RULE_GROUP = "wespan-canvas"

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_ID
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/wespan-{os.getuid()}")) / APP_ID
SETTINGS_FILE = CONFIG_DIR / "settings.json"
STATE_FILE = RUNTIME_DIR / "state.json"
# gardés d'une session à l'autre : le fond Plasma les affiche avant que le service ait démarré
CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_ID
FRAME_FILE = CACHE_DIR / "last-frame.jpg"            # dernière image de la scène (fenêtre WE entière)
LAST_STATE_FILE = CACHE_DIR / "last-state.json"
LOG_FILE = RUNTIME_DIR / "wespan.log"

DEFAULTS = {
    "wallpaper": "",                 # id Workshop (dossier) du fond affiché
    "volume": 100,
    "muted": False,
    "fps": 60,
    # pause automatique : l'image reste affichée, figée
    "pause_enabled": True,
    "pause_on_maximized": True,
    "pause_on_fullscreen": True,
    "pause_on_coverage": False,
    "coverage_threshold": 90,        # % de l'écran recouvert par des fenêtres
    "pause_scope": "all",            # "all" : quand tous les écrans sont couverts ; "any" : dès qu'un l'est
    "pause_on_lock": True,           # écran verrouillé / économiseur
    "pause_delay_ms": 800,
    # démarrage
    "start_engine": True,            # lancer Wallpaper Engine (via Steam) avec le service
    "restart_engine": True,          # le relancer s'il se ferme
    # écrans : décalage (px) de l'image pour chaque sortie, ex. {"HDMI-A-1": {"x": 0, "y": 40}}
    "offsets": {},
    # rendu : taille de la fenêtre WE (auto = rectangle englobant tous les écrans vus)
    "canvas_auto": True,
    "canvas": [0, 0],
    # zone réellement rendue par WE pour une taille de fenêtre donnée ("WxH": [w, h])
    "content": {},
    "language": "auto",
    "language_chosen": False,        # la fenêtre « choisissez votre langue » a été vue
    "tray_icon": True,               # icône dans la zone de notification (fermer la fenêtre = la réduire)
    "native_video": True,            # fonds vidéo lus par Plasma (décodage GPU) plutôt que par WE/Proton
    "quit_engine_for_video": True,   # fermer Wallpaper Engine quand le fond est une vidéo (inutile alors)
    "steam_api_key": "",             # clé Steam Web API, pour chercher dans le Workshop (page Rechercher)
    "proton": "",                    # chemin du script proton (auto-détecté si vide)
}


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_FILE.read_text()))
    except (OSError, ValueError):
        _migrate_v1(data)
    return data


def save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: data[k] for k in DEFAULTS if k in data}, indent=1, ensure_ascii=False))
    tmp.replace(SETTINGS_FILE)


def _migrate_v1(data: dict) -> None:
    """Reprend les réglages du premier prototype (fichiers séparés)."""
    def rd(name):
        try:
            return (CONFIG_DIR / name).read_text().strip()
        except OSError:
            return None
    if (v := rd("current")):
        data["wallpaper"] = v
    if (v := rd("volume")) and v.isdigit():
        data["volume"] = int(v)
    if (v := rd("muted")):
        data["muted"] = v == "1"
    try:
        data["offsets"] = json.loads((CONFIG_DIR / "layout.json").read_text()).get("offsets", {})
    except (OSError, ValueError):
        pass


def load_last_state() -> dict:
    try:
        return json.loads(LAST_STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def language(data: dict) -> str:
    from .i18n import resolve
    return resolve(data.get("language", "auto"))
