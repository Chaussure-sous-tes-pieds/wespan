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
    libraryChanged = Signal()
    _metaDone = Signal("QVariantMap")

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
        self._meta = self._load_meta()            # détails du Workshop (popularité, résolution…)
        self._metaDone.connect(self._on_meta)
        self._meta_running = False
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
            lib = lambda d: [(d.get("settings") or {}).get(k) for k in ("favorites", "folders", "wallpaper_props")]
            changed_lib = lib(st) != lib(self._state)
            self._state = st
            if changed_lib:
                self.libraryChanged.emit()
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
        items = self._meta.get("items", {})
        for w in data:
            m = items.get(w["id"])
            if m:
                w.update({"subs": m.get("subs", 0), "favorited": m.get("favorited", 0), "score": m.get("score", 0),
                          "resolution": m.get("resolution", ""), "approved": m.get("approved", False),
                          "published": m.get("created", 0), "wsTags": m.get("tags", [])})
                if m.get("updated"):
                    w["updated"] = m["updated"]
        self._wallpapers = data
        self.wallpapersChanged.emit()
        self.refreshMeta()

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

    # --- détails du Workshop pour la bibliothèque (tri par popularité, résolution…) ------------

    META_FILE = S.CACHE_DIR / "workshop-meta.json"
    META_MAX_AGE = 24 * 3600

    def _load_meta(self):
        try:
            return json.loads(self.META_FILE.read_text())
        except (OSError, ValueError):
            return {"items": {}, "fetched": {}}

    @Slot()
    def refreshMeta(self):
        """En arrière-plan : détails des fonds du Workshop inconnus ou vieux d'un jour."""
        import time
        if self._meta_running or time.time() - getattr(self, "_meta_tried", 0) < 600:
            return            # (hors ligne : un essai toutes les 10 min au plus)
        self._meta_tried = time.time()
        fetched = self._meta.get("fetched", {})
        now = time.time()
        ids = [w["id"] for w in self._wallpapers if w.get("source") == "workshop" and w["id"].isdigit()
               and now - fetched.get(w["id"], 0) > self.META_MAX_AGE]
        if not ids:
            return
        self._meta_running = True
        key = (self._state.get("settings") or S.load()).get("steam_api_key", "")

        def run():
            from .. import workshop
            try:
                got = workshop.details_many(ids, key)
            except workshop.WorkshopError:
                got = {}
            self._metaDone.emit({"got": got, "ids": ids, "time": time.time()})
        threading.Thread(target=run, daemon=True).start()

    def _on_meta(self, res):
        self._meta_running = False
        got = res.get("got") or {}
        if not got:
            return
        self._meta.setdefault("items", {}).update(got)
        for i in res.get("ids") or []:          # (y compris ceux retirés du Workshop : pas de nouvel essai)
            self._meta.setdefault("fetched", {})[i] = res["time"]
        try:
            S.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.META_FILE.write_text(json.dumps(self._meta, ensure_ascii=False))
        except OSError:
            pass
        self.refreshWallpapers()

    # --- bibliothèque : favoris et dossiers -------------------------------------------------

    def _cfg_now(self):
        return self._state.get("settings") or S.load()

    def _put(self, key, value):
        """Réglage écrit par le service s'il tourne, sinon directement."""
        if not self._call("SetSetting", key, json.dumps(value)):
            cfg = S.load(); cfg[key] = value; S.save(cfg)
        self.poll()
        self.libraryChanged.emit()

    # (copies profondes : modifier la copie ne doit pas toucher _state, sinon poll() ne voit aucun
    # changement et l'interface ne se rafraîchit pas)
    @Property("QVariantList", notify=libraryChanged)
    def favorites(self):
        return list(self._cfg_now().get("favorites") or [])

    @Property("QVariantList", notify=libraryChanged)
    def folders(self):
        import copy
        return copy.deepcopy(list(self._cfg_now().get("folders") or []))

    @Slot(str)
    def toggleFavorite(self, wid):
        fav = self.favorites
        fav.remove(wid) if wid in fav else fav.append(wid)
        self._put("favorites", fav)

    @Slot(str, result=bool)
    def createFolder(self, name):
        name = name.strip()
        folders = self.folders
        if not name or any(f["name"] == name for f in folders):
            return False
        folders.append({"name": name, "ids": []})
        self._put("folders", folders)
        return True

    @Slot(str, str, result=bool)
    def renameFolder(self, old, new):
        new = new.strip()
        folders = self.folders
        if not new or any(f["name"] == new for f in folders):
            return False
        for f in folders:
            if f["name"] == old:
                f["name"] = new
        self._put("folders", folders)
        return True

    @Slot(str)
    def deleteFolder(self, name):
        self._put("folders", [f for f in self.folders if f["name"] != name])

    @Slot(str, str)
    def moveToFolder(self, wid, name):
        """Un fond est dans un dossier au plus ; name vide = le sortir de son dossier."""
        folders = self.folders
        for f in folders:
            f["ids"] = [i for i in f.get("ids", []) if i != wid]
            if f["name"] == name:
                f["ids"].append(wid)
        self._put("folders", folders)

    @Slot(str, bool)
    def setFolderHidden(self, name, hidden):
        """Dossier exclu de la vue « Tous » (ses fonds ne s'affichent plus que dans le dossier)."""
        folders = self.folders
        for f in folders:
            if f["name"] == name:
                f["hidden"] = bool(hidden)
        self._put("folders", folders)

    @Slot(str, int)
    def moveFolder(self, name, delta):
        folders = self.folders
        i = next((k for k, f in enumerate(folders) if f["name"] == name), -1)
        j = i + delta
        if i < 0 or not 0 <= j < len(folders):
            return
        folders[i], folders[j] = folders[j], folders[i]
        self._put("folders", folders)

    # --- réglages personnalisables d'un fond ------------------------------------------------

    @Slot(str, result="QVariantList")
    def wallpaperProperties(self, wid):
        from .. import props
        w = next((x for x in self._wallpapers if x["id"] == wid), None)
        if not w:
            return []
        over = (self._cfg_now().get("wallpaper_props") or {}).get(wid, {})
        items = props.load(Path(w["path"]), over, self._lang)
        for i in items:
            if i["type"] == "color":
                i["hex"] = props.color_to_hex(i["value"])
        return items

    @Slot(str, str, "QVariant")
    def setWallpaperProperty(self, wid, key, value):
        from .. import props
        if hasattr(value, "toVariant"):
            value = value.toVariant()
        if isinstance(value, str) and value.startswith("#"):
            value = props.hex_to_color(value)
        if not self._call("SetWallpaperProperty", wid, key, json.dumps(value)):
            cfg = S.load(); cfg.setdefault("wallpaper_props", {}).setdefault(wid, {})[key] = value; S.save(cfg)
        self.poll()
        self.libraryChanged.emit()

    @Slot(str)
    def resetWallpaperProperties(self, wid):
        if not self._call("ResetWallpaperProperties", wid):
            cfg = S.load(); cfg.get("wallpaper_props", {}).pop(wid, None); S.save(cfg)
        self.poll()
        self.libraryChanged.emit()

    @Slot(str)
    def openWorkshopPage(self, wid):
        from .. import workshop
        subprocess.Popen(["steam", workshop.page_url(wid)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

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

    @Property("QVariantMap", constant=True)
    def workshopTags(self):
        from .. import workshop
        return {"genres": list(workshop.GENRES), "resolutions": list(workshop.RESOLUTIONS)}

    @Slot(str, str, int, str, str)
    def workshopSearch(self, text, sort, page, kind, rating):
        self.workshopSearchEx(text, sort, page, kind, rating, [], 7)

    @Slot(str, str, int, str, str, "QVariantList", int)
    def workshopSearchEx(self, text, sort, page, kind, rating, tags, days):
        from .. import workshop
        self._ws_seq += 1
        seq = self._ws_seq
        self._ws_busy, self._ws_error = True, ""
        self.workshopChanged.emit()
        key = (self._state.get("settings") or S.load()).get("steam_api_key", "")

        def run():
            try:
                res = workshop.search(text, sort, max(1, page), kind, rating, key, list(tags or []), days)
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
        self.a_reload = QAction(QIcon.fromTheme("view-refresh"), "", self.menu)
        self.a_quit = QAction(QIcon.fromTheme("application-exit"), "", self.menu)
        self.a_show.triggered.connect(self.show_window)
        self.a_pause.triggered.connect(lambda: backend.setPaused(not backend.state.get("paused")))
        self.a_mute.triggered.connect(lambda: backend.setMuted(not backend.state.get("muted")))
        self.a_reload.triggered.connect(backend.restartEngine)
        self.a_quit.triggered.connect(app.quit)
        for a in (self.a_show, None, self.a_pause, self.a_mute, self.a_reload, None, self.a_quit):
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
        self.a_reload.setText(t("Recharger le fond (redémarre Wallpaper Engine)",
                                "Reload wallpaper (restarts Wallpaper Engine)"))
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
    # captures de développement : ouvrir aussi la fenêtre « Personnaliser » de ce fond
    engine.rootContext().setContextProperty("shotProps", os.environ.get("WESPAN_SHOT_PROPS", "") if shots else "")
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
    pages = [x for x in os.environ.get("WESPAN_SHOT_PAGES", "").split(",") if x] or \
        ["Wallpapers", "Search", "Playback", "Audio", "Screens", "Performance", "Startup", "Diagnostic", "About"]
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
