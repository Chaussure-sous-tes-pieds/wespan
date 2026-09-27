"""Installation / réparation de l'intégration, et diagnostic."""
import shutil
import subprocess
import time
from pathlib import Path

from . import desktop, steam
from .settings import DBUS_NAME, KWIN_SCRIPT_ID, PLUGIN_ID, STATE_FILE


def share_dir() -> Path | None:
    """Dossier contenant kwin/ et plasma/ (dépôt source, installation utilisateur ou système)."""
    here = Path(__file__).resolve()
    for c in (here.parents[2], Path.home() / ".local/share/wespan", Path("/usr/share/wespan")):
        if (c / "plasma" / PLUGIN_ID / "metadata.json").exists():
            return c
    return None


def exe() -> str:
    return shutil.which("wespan") or str(Path.home() / ".local/bin/wespan")


def service_running() -> bool:
    try:
        import dbus
        return bool(dbus.SessionBus().name_has_owner(DBUS_NAME))
    except Exception:
        return False


def start_service() -> None:
    subprocess.Popen([exe(), "daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def _system_package(kind_dir: str, pid: str) -> bool:
    return (Path("/usr/share") / kind_dir / pid / "metadata.json").exists()


def _same_tree(a: Path, b: Path) -> bool:
    import filecmp
    if not b.is_dir():
        return False
    fa = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    return fa == fb and all(filecmp.cmp(a / f, b / f, shallow=False) for f in fa)


def install_packages(log=print) -> bool:
    """Installe/met à jour le script KWin et le fond d'écran Plasma (seulement s'ils ont changé).
    Retourne True si le script KWin a changé (à recharger)."""
    kwin_changed = False
    sd = share_dir()
    if not sd:
        log("✘ WE Span files not found")
        return False
    user = Path.home() / ".local/share"
    if not _system_package("kwin/scripts", KWIN_SCRIPT_ID) and \
            not _same_tree(sd / "kwin" / KWIN_SCRIPT_ID, user / "kwin/scripts" / KWIN_SCRIPT_ID):
        ok = desktop.install_package("KWin/Script", sd / "kwin" / KWIN_SCRIPT_ID)
        kwin_changed = ok
        log(("✔" if ok else "✘") + " KWin script installed")
    if not _system_package("plasma/wallpapers", PLUGIN_ID) and \
            not _same_tree(sd / "plasma" / PLUGIN_ID, user / "plasma/wallpapers" / PLUGIN_ID):
        upgrade = desktop.plugin_installed()
        ok = desktop.install_package("Plasma/Wallpaper", sd / "plasma" / PLUGIN_ID)
        log(("✔" if ok else "✘") + " Plasma wallpaper plugin installed")
        if ok and upgrade and PLUGIN_ID in desktop.plasma_plugins():
            # plasmashell garde le QML compilé en mémoire : redémarrage pour charger la mise à jour
            subprocess.run(["systemctl", "--user", "restart", "plasma-plasmashell"], timeout=30)
            time.sleep(6)
            log("✔ Plasma reloaded")
    return kwin_changed


def fix_steam_option(log=print) -> bool:
    """Steam réécrit localconfig.vdf en quittant : on le ferme, on modifie, on le relance."""
    info = steam.SteamInfo()
    if not info.root:
        log("✘ Steam not found")
        return False
    was_running = steam.steam_running()
    if was_running:
        log("… closing Steam")
        subprocess.run(["steam", "-shutdown"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(90):
            if not steam.steam_running():
                break
            time.sleep(1)
        time.sleep(3)
        if steam.steam_running():
            log("✘ Steam did not close")
            return False
    n = steam.set_launch_option(info)
    log(f"✔ launch option added ({n} account(s))" if n else "✔ launch option already set")
    if was_running:
        subprocess.Popen(["steam", "-silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        log("… Steam restarted")
    return True


def setup(steam_option: bool = False, log=print) -> None:
    kwin_changed = install_packages(log)
    if kwin_changed or not (desktop.kwin_script_enabled() and desktop.kwin_script_loaded()):
        desktop.enable_kwin_script(True)
    log("✔ KWin script running")
    desktop.set_autostart(True, exe())
    from .settings import load
    if load().get("tray_icon", True) and not desktop.AUTOSTART_TRAY.exists():
        desktop.set_tray_autostart(True, exe())
    log("✔ start with the session: enabled")
    info = steam.SteamInfo()
    if info.compatdata and info.library and not steam.drive_s_ok(info):
        steam.fix_drive_s(info)
        log("✔ Wine prefix S: drive repaired")
    if not service_running():
        start_service()
        log("✔ service started")
    time.sleep(2)
    if not desktop.plasma_active():
        desktop.apply_plasma(True)
    log("✔ WE Span wallpaper active on every screen")
    if steam_option:
        fix_steam_option(log)
    elif not steam.launch_option_ok(info):
        log("! Steam launch option missing: run again with --steam (Steam will be closed and restarted)")


def fix(what: str, log=print) -> None:
    info = steam.SteamInfo()
    if what == "packages":
        install_packages(log)
    elif what == "kwin":
        install_packages(log)
        desktop.enable_kwin_script(True)
    elif what == "plasma":
        desktop.apply_plasma(True)
    elif what == "autostart":
        desktop.set_autostart(True, exe())
    elif what == "drive":
        steam.fix_drive_s(info)
    elif what == "steam_option":
        fix_steam_option(log)
    elif what == "service":
        start_service()


def doctor() -> list[dict]:
    info = steam.SteamInfo()
    out = []

    def add(id_, ok, fr, en, fix=None, detail=""):
        out.append({"id": id_, "ok": bool(ok), "label_fr": fr, "label_en": en, "fix": None if ok else fix,
                    "detail": detail})

    tools = [t for t in ("wmctrl", "xprop", "pactl", "kpackagetool6", "kwriteconfig6", "kreadconfig6", "steam")
             if not shutil.which(t)]
    if not (shutil.which("qdbus6") or shutil.which("qdbus-qt6") or shutil.which("qdbus")):
        tools.append("qdbus6")
    add("tools", not tools, "Outils système présents", "Required tools present",
        detail=("manquants : " + ", ".join(tools)) if tools else "")
    add("steam", info.root, "Steam trouvé", "Steam found", detail=str(info.root or ""))
    add("we", info.we_dir, "Wallpaper Engine installé", "Wallpaper Engine installed", detail=str(info.we_dir or ""))
    add("proton", info.proton and info.proton.exists(), "Proton trouvé", "Proton found",
        detail=str(info.proton or "lancez WE une fois depuis Steam"))
    add("steam_option", steam.launch_option_ok(info),
        "Option de lancement Steam (WINE_DISABLE_FULLSCREEN_HACK=1)",
        "Steam launch option (WINE_DISABLE_FULLSCREEN_HACK=1)", fix="steam_option",
        detail="; ".join(o or "(vide)" for o in steam.launch_options(info)))
    add("drive", info.compatdata and steam.drive_s_ok(info), "Lecteur S: du préfixe Wine", "Wine prefix drive S:",
        fix="drive")
    add("kwin", desktop.kwin_script_installed() and desktop.kwin_script_enabled() and desktop.kwin_script_loaded(),
        "Script KWin installé et actif", "KWin script installed and running", fix="kwin")
    add("plugin", desktop.plugin_installed(), "Fond d'écran Plasma installé", "Plasma wallpaper plugin installed",
        fix="packages")
    add("plasma", desktop.plasma_active(), "Fond d'écran « WE Span » sur tous les écrans",
        "“WE Span” wallpaper on every screen", fix="plasma", detail=", ".join(desktop.plasma_plugins()))
    add("autostart", desktop.autostart_enabled(), "Démarrage automatique", "Start with the session", fix="autostart")
    running = service_running()
    add("service", running, "Service WE Span actif", "WE Span service running", fix="service")
    try:
        import json
        st = json.loads(STATE_FILE.read_text()) if running else {}
    except (OSError, ValueError):
        st = {}
    add("engine", st.get("running"), "Wallpaper Engine lancé", "Wallpaper Engine running")
    add("window", st.get("uuid"), "Fenêtre de rendu trouvée", "Render window found", detail=st.get("uuid", ""))
    return out
