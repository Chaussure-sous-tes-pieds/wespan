"""Application de réglages WE Span (PySide6 + Kirigami)."""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401 (type exact des fenêtres QML)

from .. import __version__, desktop, settings as S
from ..settings import DBUS_IFACE, DBUS_NAME, DBUS_PATH, LOG_FILE


class Backend(QObject):
    stateChanged = Signal()
    wallpapersChanged = Signal()
    diagnosticsChanged = Signal()
    busyChanged = Signal()
    toast = Signal(str)

    def __init__(self):
        super().__init__()
        self._state = {}
        self._wallpapers = []
        self._diag = []
        self._busy = ""
        self._iface = None
        self._lang = S.language(S.load())
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        self._timer.start(1000)
        self.poll()
        self.refreshWallpapers()
        self.refreshDiagnostics()

    # --- service --------------------------------------------------------------------------

    def _d(self):
        import dbus
        if self._iface is None:
            bus = dbus.SessionBus()
            self._iface = dbus.Interface(bus.get_object(DBUS_NAME, DBUS_PATH), DBUS_IFACE)
        return self._iface

    def _call(self, method, *args):
        try:
            return getattr(self._d(), method)(*args, timeout=10)
        except Exception:
            self._iface = None
            return None

    @Slot()
    def poll(self):
        raw = self._call("GetState")
        st = json.loads(raw) if raw else {}
        if st != self._state:
            self._state = st
            if st.get("lang"):
                self._lang = st["lang"]
            self.stateChanged.emit()

    @Property("QVariantMap", notify=stateChanged)
    def state(self):
        return self._state

    @Property(bool, notify=stateChanged)
    def serviceRunning(self):
        return bool(self._state)

    @Property("QVariantMap", notify=stateChanged)
    def cfg(self):
        return self._state.get("settings", {})

    @Property(str, notify=stateChanged)
    def lang(self):
        return self._lang

    @Property(str, constant=True)
    def version(self):
        return __version__

    # --- fonds ----------------------------------------------------------------------------

    @Property("QVariantList", notify=wallpapersChanged)
    def wallpapers(self):
        return self._wallpapers

    @Slot()
    def refreshWallpapers(self):
        raw = self._call("ListWallpapers")
        if raw is None:
            from ..steam import SteamInfo, list_wallpapers
            data = list_wallpapers(SteamInfo())
        else:
            data = json.loads(raw)
        self._wallpapers = data
        self.wallpapersChanged.emit()

    @Slot(str)
    def setWallpaper(self, wid):
        if self._call("SetWallpaper", wid):
            self.toast.emit("wallpaper")
        self.poll()

    # --- réglages -------------------------------------------------------------------------

    @Slot(str, "QVariant")
    def setSetting(self, key, value):
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        self._call("SetSetting", key, json.dumps(value))
        self.poll()

    @Slot(int)
    def setVolume(self, v):
        self._call("SetVolume", int(v))

    @Slot(bool)
    def setMuted(self, m):
        self._call("SetMuted", bool(m))
        self.poll()

    @Slot(bool)
    def setPaused(self, p):
        self._call("SetPaused", bool(p))
        self.poll()

    @Slot(str, int, int)
    def setOffset(self, screen, x, y):
        self._call("SetOffset", screen, int(x), int(y))

    @Slot()
    def restartEngine(self):
        self._call("RestartEngine")
        self.toast.emit("restart")

    @Slot()
    def startEngine(self):
        self._call("StartEngine")

    @Slot()
    def stopEngine(self):
        self._call("StopEngine")

    # --- démarrage ------------------------------------------------------------------------

    @Property(bool, notify=diagnosticsChanged)
    def autostart(self):
        return desktop.autostart_enabled()

    @Slot(bool)
    def setAutostart(self, on):
        from ..setup import exe
        desktop.set_autostart(on, exe())
        self.refreshDiagnostics()

    trayChanged = Signal()

    @Property(bool, notify=trayChanged)
    def trayEnabled(self):
        cfg = self._state.get("settings") or S.load()
        return bool(cfg.get("tray_icon", True))

    @Slot(bool)
    def setTrayEnabled(self, on):
        from ..setup import exe
        self.setSetting("tray_icon", bool(on))
        if not self._state:                      # service arrêté : on écrit le réglage nous-mêmes
            cfg = S.load(); cfg["tray_icon"] = bool(on); S.save(cfg)
        desktop.set_tray_autostart(bool(on), exe())
        self.trayChanged.emit()

    @Slot()
    def startService(self):
        from ..setup import start_service
        start_service()
        QTimer.singleShot(2500, self.refreshAll)

    @Slot()
    def refreshAll(self):
        self.poll()
        self.refreshWallpapers()
        self.refreshDiagnostics()

    # --- diagnostic / réparations (dans un fil : certaines prennent du temps) --------------

    @Property("QVariantList", notify=diagnosticsChanged)
    def diagnostics(self):
        return self._diag

    @Property(str, notify=busyChanged)
    def busy(self):
        return self._busy

    def _set_busy(self, v):
        self._busy = v
        self.busyChanged.emit()

    @Slot()
    def refreshDiagnostics(self):
        from ..setup import doctor
        self._diag = doctor()
        self.diagnosticsChanged.emit()

    @Slot(str)
    def fix(self, what):
        if self._busy:
            return
        self._set_busy(what)

        def run():
            from ..setup import fix, setup
            try:
                if what == "all":
                    setup(steam_option=not any(d["ok"] for d in self._diag if d["id"] == "steam_option"),
                          log=lambda *_: None)
                else:
                    fix(what, log=lambda *_: None)
            finally:
                QTimer.singleShot(0, self._fix_done)
        threading.Thread(target=run, daemon=True).start()

    def _fix_done(self):
        self._set_busy("")
        self._iface = None
        QTimer.singleShot(1500, self.refreshAll)

    @Slot(result=str)
    def logTail(self):
        try:
            return "\n".join(Path(LOG_FILE).read_text(errors="replace").splitlines()[-200:])
        except OSError:
            return ""

    # --- divers ---------------------------------------------------------------------------

    @Slot(str)
    def openUrl(self, url):
        QDesktopServices.openUrl(QUrl(url))

    @Slot(str)
    def openFolder(self, path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    @Slot()
    def openWorkshop(self):
        subprocess.Popen(["steam", "steam://url/SteamWorkshopPage/431960"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    @Slot()
    def openDisplaySettings(self):
        subprocess.Popen(["kcmshell6", "kcm_kscreen"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    @Slot(result=str)
    def logDir(self):
        return str(Path(LOG_FILE).parent)


class Tray(QObject):
    """Icône de la zone de notification (option « tray_icon »)."""

    def __init__(self, backend, win, app):
        super().__init__()
        self.b, self.win, self.app = backend, win, app
        self.icon = QSystemTrayIcon(app.windowIcon())
        self.menu = QMenu()
        t = self.t
        self.a_show = QAction(QIcon.fromTheme("configure"), "", self.menu)
        self.a_pause = QAction("", self.menu)
        self.a_mute = QAction("", self.menu)
        self.a_quit = QAction(QIcon.fromTheme("application-exit"), "", self.menu)
        self.a_show.triggered.connect(self.show_window)
        self.a_pause.triggered.connect(lambda: backend.setPaused(not backend.state.get("paused")))
        self.a_mute.triggered.connect(lambda: backend.setMuted(not backend.state.get("muted")))
        self.a_quit.triggered.connect(app.quit)
        for a in (self.a_show, None, self.a_pause, self.a_mute, None, self.a_quit):
            self.menu.addSeparator() if a is None else self.menu.addAction(a)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self.on_activated)
        backend.stateChanged.connect(self.refresh)
        backend.trayChanged.connect(self.apply)
        self.refresh()
        self.apply()

    def t(self, fr, en):
        return fr if self.b.lang == "fr" else en

    def apply(self):
        on = self.b.trayEnabled
        self.icon.setVisible(on)
        self.app.setQuitOnLastWindowClosed(not on)

    def refresh(self):
        st, t = self.b.state, self.t
        self.a_show.setText(t("Réglages de WE Span", "WE Span settings"))
        manual = st.get("paused")
        self.a_pause.setText(t("Reprendre l'animation", "Resume animation") if manual
                             else t("Mettre le fond en pause", "Pause wallpaper"))
        self.a_pause.setIcon(QIcon.fromTheme("media-playback-start" if manual else "media-playback-pause"))
        muted = st.get("muted")
        self.a_mute.setText(t("Remettre le son", "Unmute") if muted else t("Couper le son", "Mute"))
        self.a_mute.setIcon(QIcon.fromTheme("audio-volume-high" if muted else "audio-volume-muted"))
        self.a_quit.setText(t("Quitter l'icône (le fond continue)", "Quit tray icon (wallpaper keeps running)"))
        status = (t("En pause", "Paused") if st.get("paused") else t("En lecture", "Playing")) if st else \
            t("Service arrêté", "Service stopped")
        self.icon.setToolTip("WE Span — " + status)

    def on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.win.isVisible():
                self.win.hide()
            else:
                self.show_window()

    def show_window(self):
        self.win.show()
        self.win.raise_()
        self.win.requestActivate()


def main(tray_start: bool = False):
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")
    app = QApplication(sys.argv)
    app.setApplicationName("wespan")
    app.setApplicationDisplayName("WE Span")
    app.setOrganizationDomain("wespan.org")
    app.setDesktopFileName("wespan")
    app.setWindowIcon(QIcon.fromTheme("wespan", QIcon(str(Path(__file__).parent / "wespan.svg"))))
    # une seule instance : une deuxième ouverture montre la fenêtre existante
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    shots = os.environ.get("WESPAN_SHOT_DIR")
    sock = QLocalSocket()
    if not shots:
        sock.connectToServer("wespan-settings")
    if not shots and sock.waitForConnected(300):
        if not tray_start:
            sock.write(b"raise")
            sock.flush()
            sock.waitForBytesWritten(300)
        return 0
    server = QLocalServer()
    if not shots:
        QLocalServer.removeServer("wespan-settings")
        server.listen("wespan-settings")

    backend = Backend()
    if tray_start and not backend.trayEnabled:
        return 0
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("startHidden", bool(tray_start))
    engine.load(QUrl.fromLocalFile(str(Path(__file__).parent / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    win = engine.rootObjects()[0]
    tray = Tray(backend, win, app) if not shots else None

    def raise_window():
        c = server.nextPendingConnection()
        if c:
            c.close()
        win.show()
        win.raise_()
        win.requestActivate()
    server.newConnection.connect(raise_window)
    if shots:
        _screenshots(win, shots)
    rc = app.exec()
    del tray
    return rc


def _screenshots(win, out_dir):
    """Captures de chaque page (développement / documentation) : WESPAN_SHOT_DIR=… wespan settings"""
    from PySide6.QtCore import Q_ARG, QMetaObject
    pages = ["Wallpapers", "Playback", "Audio", "Screens", "Performance", "Startup", "Diagnostic", "About"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    def step(i=0):
        if i > 0:
            win.grabWindow().save(str(Path(out_dir) / f"{i:02d}-{pages[i - 1]}.png"))
        if i == len(pages):
            QTimer.singleShot(1500, QApplication.quit)
            return
        QMetaObject.invokeMethod(win, "showPage", Q_ARG("QVariant", pages[i]))
        QTimer.singleShot(2500, lambda: step(i + 1))
    QTimer.singleShot(3000, step)
