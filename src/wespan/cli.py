"""wespan — ligne de commande (parle au service par DBus)."""
import argparse
import json
import sys

from .settings import DBUS_IFACE, DBUS_NAME, DBUS_PATH

HELP = """\
commandes :
  daemon                 lance le service (démarrage de session)
  settings [--tray]      ouvre l'application de réglages (--tray : réduite dans la zone de notification)
  status                 état (JSON)
  set <id>               change de fond (id Workshop)
  list                   fonds disponibles (JSON)
  mute | unmute | togglemute
  volume <0-150>
  pause | resume | togglepause
  offset <écran> <x> <y> décale l'image d'un écran (ex. HDMI-A-1 0 40)
  restart                relance Wallpaper Engine
  doctor                 diagnostic de l'installation
  setup [--steam]        installe/répare l'intégration KDE (--steam : option de lancement, ferme Steam)
  quit                   arrête le service
"""


def iface():
    import dbus
    bus = dbus.SessionBus()
    return dbus.Interface(bus.get_object(DBUS_NAME, DBUS_PATH), DBUS_IFACE)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wespan", description="WE Span : Wallpaper Engine comme fond d'écran Plasma",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=HELP)
    ap.add_argument("command", nargs="?", default="settings")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--steam", action="store_true")
    ap.add_argument("--tray", action="store_true", help="settings : démarrer réduit dans la zone de notification")
    a = ap.parse_args(argv)
    c, args = a.command, a.args

    if c == "daemon":
        from .daemon import main as dmain
        return dmain()
    if c == "settings":
        from .gui.app import main as gmain
        return gmain(tray_start=a.tray)
    if c == "doctor":
        from .setup import doctor
        ok = True
        for d in doctor():
            ok &= d["ok"]
            print(("✔ " if d["ok"] else "✘ ") + d["label_fr"] + (f"  — {d['detail']}" if d.get("detail") else ""))
        return 0 if ok else 1
    if c == "setup":
        from .setup import setup
        setup(steam_option=a.steam, log=print)
        return 0

    try:
        d = iface()
    except Exception:
        print("Le service WE Span ne tourne pas (lancez : wespan daemon)", file=sys.stderr)
        return 2
    if c == "status":
        print(json.dumps(json.loads(d.GetState()), indent=1, ensure_ascii=False))
    elif c == "list":
        print(d.ListWallpapers())
    elif c == "set":
        return 0 if d.SetWallpaper(args[0]) else 1
    elif c in ("mute", "unmute"):
        d.SetMuted(c == "mute")
    elif c == "togglemute":
        print("muted" if d.ToggleMute() else "unmuted")
    elif c == "volume":
        d.SetVolume(int(args[0]))
    elif c in ("pause", "resume"):
        d.SetPaused(c == "pause")
    elif c == "togglepause":
        print("paused" if d.TogglePause() else "playing")
    elif c == "offset":
        d.SetOffset(args[0], int(args[1]), int(args[2]))
    elif c == "restart":
        d.RestartEngine()
    elif c == "quit":
        d.Quit()
    else:
        ap.print_help()
        return 1
    return 0
