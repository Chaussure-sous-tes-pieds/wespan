"""Pilotage de Wallpaper Engine (processus Windows lancé par Steam/Proton)."""
import glob
import json
import logging
import os
import signal
import subprocess
from pathlib import Path

from .settings import WINDOW_TITLE, WE_APPID
from .steam import SteamInfo

log = logging.getLogger("wespan.engine")


_pid_cache = None


def we_pid() -> int | None:
    global _pid_cache
    if _pid_cache:
        try:
            if Path(f"/proc/{_pid_cache}/comm").read_text().strip() == "wallpaper64.exe":
                return _pid_cache
        except OSError:
            pass
        _pid_cache = None
    for c in glob.glob("/proc/[0-9]*/comm"):
        try:
            if Path(c).read_text().strip() == "wallpaper64.exe":
                _pid_cache = int(c.split("/")[2])
                return _pid_cache
        except (OSError, ValueError):
            pass
    return None


def is_stopped(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] in ("T", "t")
    except (OSError, IndexError):
        return False


def freeze(on: bool) -> bool:
    """Pause « image figée » : WE ne calcule plus rien (0 % CPU/GPU) mais sa dernière image reste."""
    pid = we_pid()
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGSTOP if on else signal.SIGCONT)
        return True
    except OSError:
        return False


def launch_via_steam() -> None:
    log.info("starting Wallpaper Engine through Steam")
    subprocess.Popen(["steam", "-silent", f"steam://rungameid/{WE_APPID}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def quit_engine(timeout: float = 15) -> None:
    pid = we_pid()
    if not pid:
        return
    freeze(False)
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    import time
    t = time.time()
    while we_pid() and time.time() - t < timeout:
        time.sleep(0.3)
    if (pid := we_pid()):
        os.kill(pid, signal.SIGKILL)


def win_path(info: SteamInfo, path: Path) -> str:
    """Chemin Windows tel que Steam le donne à WE (lecteur S: = bibliothèque Steam). Utiliser Z:
    ferait croire à WE qu'il a été déplacé : il réécrit alors sa configuration à chaque commande."""
    path = Path(path)
    try:
        rel = path.resolve().relative_to(info.library.resolve())
        return "S:\\" + str(rel).replace("/", "\\")
    except (ValueError, AttributeError):
        return "Z:" + str(path).replace("/", "\\")


last_control = 0.0


def control(info: SteamInfo, *args: str, timeout: float = 45) -> bool:
    """wallpaper64.exe -control … dans le même préfixe/wineserver que l'instance en cours.
    Les appels doivent être faits un par un (le Worker du service s'en charge)."""
    global last_control
    if not info.ok:
        log.error("Steam/Proton/Wallpaper Engine not found")
        return False
    freeze(False)  # un processus gelé ne répondrait pas
    last_control = __import__("time").time()
    cmd = [str(info.proton), "run", win_path(info, info.we_dir / "wallpaper64.exe"), "-control", *args]
    try:
        r = subprocess.run(cmd, env=info.env(), cwd=str(info.we_dir), stdout=subprocess.DEVNULL,
                           stderr=subprocess.PIPE, timeout=timeout, text=True)
        last_control = __import__("time").time()
        if r.returncode:
            log.warning("control %s -> exit code %s: %s", args[0], r.returncode, r.stderr[-400:])
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        log.warning("control %s: timed out", args[0])
        return False


def open_wallpaper(info: SteamInfo, project_json: Path, width: int, height: int, title: str) -> bool:
    return control(info, "openWallpaper", "-file", win_path(info, project_json),
                   "-playInWindow", title, "-width", str(width), "-height", str(height), "-borderless")


def close_wallpaper(info: SteamInfo, title: str) -> bool:
    """Ne ferme que la fenêtre portant ce titre, et attend que WE l'ait vraiment fait : une nouvelle
    commande pendant qu'il traite la précédente est ignorée (« Windows is reentrant »), voire le fait
    quitter."""
    import time
    # « -playInWindow X » fermerait TOUTES les fenêtres ; « -location X » ne ferme que X
    ok = control(info, "closeWallpaper", "-location", title)
    for _ in range(40):
        if title not in canvas_windows():
            break
        time.sleep(0.25)
    time.sleep(0.5)
    return ok


def drawn_extent(xid: str, save: Path | None = None) -> tuple | None:
    """(largeur, hauteur) de la zone que WE dessine vraiment dans sa fenêtre (voir probe.py) ; avec
    save, l'image de la fenêtre y est aussi enregistrée (JPEG)."""
    import sys
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [
        str(Path(__file__).resolve().parent.parent), os.environ.get("PYTHONPATH")])))
    try:
        r = subprocess.run([sys.executable, "-m", "wespan.probe", xid, *([str(save)] if save else [])],
                           env=env, capture_output=True, text=True, timeout=30)
        w, h = map(int, r.stdout.split())
        return w, h
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# --- fenêtres X11 (Xwayland) ----------------------------------------------------------------

def canvas_windows() -> dict:
    """{titre: xid} des fenêtres de rendu de WE Span (titres commençant par WINDOW_TITLE)."""
    try:
        out = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return {}
    wins = {}
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4 and parts[3].strip().startswith(WINDOW_TITLE):
            wins[parts[3].strip()] = parts[0]
    return wins


def window_xid(title: str | None = None) -> str | None:
    wins = canvas_windows()
    return wins.get(title) if title else next(iter(wins.values()), None)


def mark_desktop_type(xid: str) -> bool:
    """Type « bureau » : jamais masquée par « Afficher le bureau », jamais au premier plan.
    (La règle KWin équivalente est ignorée pour cette fenêtre, d'où xprop.)"""
    try:
        cur = subprocess.run(["xprop", "-id", xid, "_NET_WM_WINDOW_TYPE"], capture_output=True, text=True, timeout=5).stdout
        if "_NET_WM_WINDOW_TYPE_DESKTOP" in cur:
            return True
        subprocess.run(["xprop", "-id", xid, "-f", "_NET_WM_WINDOW_TYPE", "32a", "-set",
                        "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DESKTOP"], timeout=5, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# --- son (PipeWire / PulseAudio) ------------------------------------------------------------

def _sink_inputs() -> list:
    try:
        out = subprocess.run(["pactl", "-f", "json", "list", "sink-inputs"], capture_output=True,
                             text=True, timeout=5).stdout
        return json.loads(out or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def sink_input() -> int | None:
    for i in _sink_inputs():
        props = i.get("properties", {})
        if props.get("application.name") == "Wallpaper Engine" or \
           props.get("application.process.binary", "").startswith("wallpaper64"):
            return i["index"]
    return None


def set_audio(volume: int, muted: bool) -> bool:
    idx = sink_input()
    if idx is None:
        return False
    subprocess.run(["pactl", "set-sink-input-volume", str(idx), f"{max(0, min(150, int(volume)))}%"], timeout=5)
    subprocess.run(["pactl", "set-sink-input-mute", str(idx), "1" if muted else "0"], timeout=5)
    return True
