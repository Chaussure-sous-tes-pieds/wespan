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

from .. import __version__, desktop, i18n, settings as S
from ..settings import DBUS_IFACE, DBUS_NAME, DBUS_PATH, LOG_FILE


class Backend(QObject):
    stateChanged = Signal()
    wallpapersChanged = Signal()
    diagnosticsChanged = Signal()
    busyChanged = Signal()
    toast = Signal(str)
    workshopChanged = Signal()
    _workshopDone = Signal(int, "QVariantMap")

    def __init__(self):
        super().__init__()
        self._state = {}
        self._wallpapers = []
        self._diag = []
        self._busy = ""
        self._iface = None
        self._ws = {"items": [], "total": 0, "page": 1, "pages": 1}
        self._ws_busy = False
        self._ws_error = ""
        self._ws_seq = 0
        self._workshopDone.connect(self._on_workshop)
        # après « S'abonner » : on guette l'arrivée du fond téléchargé par Steam
        self._watch = QTimer(self)
        self._watch.timeout.connect(self._watch_downloads)
        self._watch_left = 0
        cfg = S.load()
        self._lang = S.language(cfg)
        self._chosen = bool(cfg.get("language_chosen"))
        self._catalogs = i18n.catalogs()
        self._dump = {} if os.environ.get("WESPAN_I18N_DUMP") else None
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
            if st.get("lang") and st["lang"] != self._lang and self._dump is None:
                self._lang = st["lang"]
                self.langChanged.emit()
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

    langChanged = Signal()

    @Property(str, notify=langChanged)
    def lang(self):
        return self._lang

    @Property("QVariantList", constant=True)
    def languages(self):
        return i18n.languages()

    @Property(bool, notify=langChanged)
    def languageChosen(self):
        return self._chosen

    @Slot(str)
    def setLanguage(self, code):
        """code : "auto" ou un code de langue. Appliqué tout de suite, et mémorisé."""
        cfg = S.load()
        cfg["language"], cfg["language_chosen"] = code, True
        S.save(cfg)                                    # (le service peut être arrêté)
        self._call("SetSetting", "language", json.dumps(code))
        self._call("SetSetting", "language_chosen", "true")
        self._chosen = True
        self._lang = i18n.resolve(code)
        self.langChanged.emit()
        self.poll()

    @Slot(str, result=str)
    def translate(self, en):
        """Langues autres que fr/en : texte anglais -> traduction du catalogue (sinon anglais)."""
        if self._dump is not None:
            self._dump[en] = ""
        return self._catalogs.get(self._lang, {}).get(en) or en

    def t(self, fr, en):
        return fr if self._lang == "fr" else en if self._lang == "en" else self.translate(en)

    def write_i18n_template(self):
        path = os.environ.get("WESPAN_I18N_DUMP")
        if path and self._dump is not None:
            data = {"_name": "Language name (in that language)"}
            data.update(dict(sorted(self._dump.items())))
            Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

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

    # --- recherche dans le Workshop -------------------------------------------------------

    @Property("QVariantMap", notify=workshopChanged)
    def workshop(self):
        return self._ws

    @Property(bool, notify=workshopChanged)
    def workshopBusy(self):
        return self._ws_busy

    @Property(str, notify=workshopChanged)
    def workshopError(self):
        return self._ws_error

    @Property("QVariantList", notify=wallpapersChanged)
    def installedIds(self):
        return [w["id"] for w in self._wallpapers]

    @Slot(str, str, int, str, str)
    def workshopSearch(self, text, sort, page, kind, rating):
        from .. import workshop
        self._ws_seq += 1
        seq = self._ws_seq
        self._ws_busy, self._ws_error = True, ""
        self.workshopChanged.emit()
        key = (self._state.get("settings") or S.load()).get("steam_api_key", "")

        def run():
            try:
                res = workshop.search(text, sort, max(1, page), kind, rating, key)
            except workshop.WorkshopError as e:
                res = {"error": str(e)}
            self._workshopDone.emit(seq, res)
        threading.Thread(target=run, daemon=True).start()

    def _on_workshop(self, seq, res):
        if seq != self._ws_seq:
            return                                   # réponse d'une recherche déjà remplacée
        self._ws_busy = False
        if "error" in res:
            self._ws_error = res["error"]
        else:
            self._ws = res
        self.workshopChanged.emit()

    @Slot(str)
    def setApiKey(self, key):
        key = key.strip()
        if not self._call("SetSetting", "steam_api_key", json.dumps(key)):
            cfg = S.load(); cfg["steam_api_key"] = key; S.save(cfg)
        self.poll()

    @Slot(str)
    def openWorkshopItem(self, wid):
        from .. import workshop
        subprocess.Popen(["steam", workshop.page_url(wid)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        self._watch_left = 120                       # 10 min
        self._watch.start(5000)

    def _watch_downloads(self):
        self._watch_left -= 1
        before = set(self.installedIds)
        self.refreshWallpapers()
        if set(self.installedIds) - before:
            self.toast.emit("downloaded")
        if self._watch_left <= 0:
            self._watch.stop()

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
        backend.langChanged.connect(self.refresh)
        self.refresh()
        self.apply()

    def t(self, fr, en):
        return self.b.t(fr, en)

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
    engine.rootContext().setContextProperty("shotMode", bool(shots))
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
    backend.write_i18n_template()
    del tray
    return rc


def _screenshots(win, out_dir):
    """Captures de chaque page (développement / documentation) : WESPAN_SHOT_DIR=… wespan settings"""
    from PySide6.QtCore import Q_ARG, QMetaObject
    pages = ["Wallpapers", "Search", "Playback", "Audio", "Screens", "Performance", "Startup", "Diagnostic", "About"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    def step(i=0):
        if i > 0:
            win.grabWindow().save(str(Path(out_dir) / f"{i:02d}-{pages[i - 1]}.png"))
        if i == len(pages):
            QMetaObject.invokeMethod(win, "openLangDialog")
            QTimer.singleShot(1500, lambda: (win.grabWindow().save(str(Path(out_dir) / f"{i + 1:02d}-Language.png")),
                                             QApplication.quit()))
            return
        QMetaObject.invokeMethod(win, "showPage", Q_ARG("QVariant", pages[i]))
        QTimer.singleShot(2500, lambda: step(i + 1))
    QTimer.singleShot(3000, step)
