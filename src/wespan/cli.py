"""wespan — ligne de commande (parle au service par DBus)."""
import argparse
import json
import sys

from .settings import DBUS_IFACE, DBUS_NAME, DBUS_PATH

HELP = """\
commands:
  daemon                 run the service (started with your session)
  settings [--tray]      open the settings app (--tray: start hidden in the system tray)
  status                 current state (JSON)
  set <id>               switch wallpaper (Workshop id)
  list                   available wallpapers (JSON)
  mute | unmute | togglemute
  volume <0-150>
  pause | resume | togglepause
  offset <screen> <x> <y>  shift one screen's part of the picture (e.g. HDMI-A-1 0 40)
  restart                restart Wallpaper Engine
  doctor                 check the installation
  setup [--steam]        install/repair the KDE integration (--steam: also set the Steam launch option; closes Steam)
  quit                   stop the service
  i18n-template [file]   write the list of strings to translate (see src/wespan/i18n.py)
"""


def iface():
    import dbus
    bus = dbus.SessionBus()
    return dbus.Interface(bus.get_object(DBUS_NAME, DBUS_PATH), DBUS_IFACE)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wespan", description="WE Span: Wallpaper Engine as a real KDE Plasma wallpaper",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=HELP)
    ap.add_argument("command", nargs="?", default="settings")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--steam", action="store_true")
    ap.add_argument("--tray", action="store_true", help="settings: start hidden in the system tray")
    a = ap.parse_args(argv)
    c, args = a.command, a.args

    if c == "daemon":
        from .daemon import main as dmain
        return dmain()
    if c == "settings":
        from .gui.app import main as gmain
        return gmain(tray_start=a.tray)
    if c == "i18n-template":
        import os, tempfile
        out = os.path.abspath(args[0] if args else "wespan-template.json")
        os.environ.update({"WESPAN_I18N_DUMP": out, "WESPAN_LANG": "_template",
                           "WESPAN_SHOT_DIR": tempfile.mkdtemp(prefix="wespan-i18n-"),
                           "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"})
        from .gui.app import main as gmain
        gmain()
        print(f"{out}: " + str(len(__import__("json").load(open(out))) - 1) + " strings")
        return 0
    if c == "doctor":
        from .setup import doctor
        from .settings import language, load
        key = "label_fr" if language(load()) == "fr" else "label_en"
        ok = True
        for d in doctor():
            ok &= d["ok"]
            print(("✔ " if d["ok"] else "✘ ") + d[key] + (f"  — {d['detail']}" if d.get("detail") else ""))
        return 0 if ok else 1
    if c == "setup":
        from .setup import setup
        setup(steam_option=a.steam, log=print)
        return 0

    try:
        d = iface()
    except Exception:
        print("The WE Span service is not running (start it with: wespan daemon)", file=sys.stderr)
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
