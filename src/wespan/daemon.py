"""Service WE Span : supervise Wallpaper Engine, pause automatique, son, écrans, état pour le plugin."""
import json
import logging
import os
import queue
import signal
import sys
import threading
import time

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

from . import desktop, engine, media, overlay, settings as S, steam
from .settings import DBUS_IFACE, DBUS_NAME, DBUS_PATH, RUNTIME_DIR, STATE_FILE, WINDOW_TITLE

log = logging.getLogger("wespan")

TICK_S = 3
LAUNCH_COOLDOWN = 90        # s entre deux lancements de WE
STEAM_WAIT = 60             # s laissés à Steam pour lancer WE, avant de le lancer nous-mêmes par Proton
OPEN_COOLDOWN = 30          # s entre deux réouvertures de la fenêtre
WE_WARMUP = 12              # s laissés à WE pour démarrer avant d'ouvrir un fond
GRACE_S = 6                 # s de lecture garantis après l'ouverture d'un fond (avant une éventuelle pause)
LAYOUT_SETTLE = 8           # s de disposition d'écrans stable avant de recréer la fenêtre
X_SCREEN_WAIT = 30          # s max à attendre que l'écran Xwayland ait la nouvelle taille
VERIFY_WINDOW = 600         # s après un changement d'écrans pendant lesquels on vérifie chaque ouverture
VERIFY_DELAY = 5            # s après l'ouverture avant de mesurer ce que WE dessine
REOPEN_DELAYS = (10, 20, 40, 60, 120, 240)   # s avant chaque nouvel essai si WE dessine trop petit
VIDEO_QUIT_DELAY = 60       # s de fond vidéo avant de fermer WE (inutile pour une vidéo)
LONG_PAUSE = 120            # s : au-delà, on rouvre la scène à la reprise (horloges des fonds en retard)
SNAPSHOT_EVERY = 600        # s entre deux captures de la dernière image (affichée à l'ouverture de session)


class Worker(threading.Thread):
    """Exécute les opérations lentes (commandes Proton…) une par une, hors de la boucle DBus."""

    def __init__(self):
        super().__init__(daemon=True)
        self.q = queue.Queue()
        self.busy = False

    def submit(self, name, fn, done=None):
        self.q.put((name, fn, done))

    def run(self):
        while True:
            name, fn, done = self.q.get()
            self.busy = True
            try:
                res = fn()
            except Exception:
                log.exception("task %s", name)
                res = None
            self.busy = False
            if done:
                GLib.idle_add(lambda: (done(res), False)[1])


class Daemon(dbus.service.Object):
    def __init__(self, bus):
        self.cfg = S.load()
        self.info = steam.SteamInfo(self.cfg.get("proton", ""))
        self.worker = Worker()
        self.worker.start()
        self.screens = []                    # rapporté par le script KWin
        self.uuids = {}                      # titre de fenêtre -> uuid KWin (rapporté par le script)
        self.title = ""                      # fenêtre affichée (les autres sont en cours d'ouverture/fermeture)
        self.xid = None
        self.xid_marked = set()
        self.grace_until = 0.0               # le nouveau fond joue quelques secondes avant toute pause
        # fonds vidéo lus nativement par le plugin : horloge commune à tous les écrans
        self.video_epoch = time.time()
        self.video_paused_pos = None
        self.window_size = None              # taille avec laquelle la fenêtre a été créée
        self.manual_pause = False
        self.resume_override = False
        self.paused = False                  # état réellement appliqué (SIGSTOP)
        self.want_since = 0.0
        self.pause_reason = ""
        self.locked = False
        self.showing_desktop = False
        self.user_stopped = False
        self.last_launch = 0.0
        self.last_open = 0.0
        self.we_seen_since = 0.0
        self.sink_idx = None
        self.layout_changed = 0.0
        self.verify_at = 0.0                 # mesure prévue de la zone dessinée par WE
        self.reopen_at = 0.0                 # réouverture prévue (WE dessinait trop petit)
        self.bad_renders = 0
        self.video_since = 0.0
        self.last_snapshot = 0.0
        self.last_persist = ""
        self.paused_since = 0.0
        self.steam_launch_at = 0.0
        self.direct_tried = False
        self.loops = {}                      # vidéo -> version allongée (None : en cours / inutile)
        # dernière image gardée, et horloge vidéo de la session précédente (le fond Plasma a pu
        # commencer à jouer la vidéo avant le démarrage du service : on garde la même horloge)
        last = S.load_last_state()
        self.frame = last.get("frameInfo") if S.FRAME_FILE.is_file() else None
        if (last.get("video") or {}).get("epoch") and last.get("wallpaper") == self.cfg["wallpaper"]:
            self.video_epoch = last["video"]["epoch"] / 1000
        self.open_pending = False
        self.opened_wallpaper = None
        self.last_audio_check = 0.0
        self.rev = 0
        self.last_state = ""
        self.message = ""
        super().__init__(dbus.service.BusName(DBUS_NAME, bus, do_not_queue=True), DBUS_PATH)
        self._watch_session(bus)
        GLib.timeout_add_seconds(TICK_S, self.tick)
        GLib.timeout_add(1000, self.pause_tick)   # + à chaque rapport du script KWin
        GLib.idle_add(self.startup)

    # --- démarrage ------------------------------------------------------------------------

    def startup(self):
        if not self.info.ok:
            self.message = "steam_missing"
            log.error("Steam / Wallpaper Engine / Proton not found")
        if self.info.compatdata and self.info.library and not steam.drive_s_ok(self.info):
            try:
                steam.fix_drive_s(self.info)
                log.info("re-created the prefix S: drive")
            except OSError:
                pass
        if not self.cfg["wallpaper"]:
            wps = steam.list_wallpapers(self.info)
            if wps:
                self.cfg["wallpaper"] = wps[0]["id"]
        if not self.screens:
            self.screens = self._screens_from_plasma()
        self.write_state()
        self.tick()
        return False

    def _screens_from_plasma(self):
        out = desktop.plasma_eval(
            'var r=[]; for (var i=0;i<screenCount;i++){var g=screenGeometry(i); r.push(g.x+","+g.y+","+g.width+","+g.height);} print(r.join(";"));')
        scr = []
        for i, part in enumerate(p for p in out.split(";") if p):
            try:
                x, y, w, h = map(int, part.split(","))
                scr.append({"name": f"screen{i}", "x": x, "y": y, "w": w, "h": h, "cover": 0,
                            "maximized": False, "fullscreen": False})
            except ValueError:
                pass
        return scr

    def _watch_session(self, bus):
        try:
            bus.add_signal_receiver(self._on_lock, "ActiveChanged", "org.freedesktop.ScreenSaver")
            ss = bus.get_object("org.freedesktop.ScreenSaver", "/ScreenSaver")
            self.locked = bool(ss.GetActive(dbus_interface="org.freedesktop.ScreenSaver"))
        except dbus.DBusException:
            pass
        try:
            bus.add_signal_receiver(self._on_show_desktop, "showingDesktopChanged", "org.kde.KWin",
                                    path="/KWin")
            kwin = bus.get_object("org.kde.KWin", "/KWin")
            self.showing_desktop = bool(kwin.Get("org.kde.KWin", "showingDesktop",
                                                 dbus_interface="org.freedesktop.DBus.Properties"))
        except dbus.DBusException:
            pass

    def _on_lock(self, active):
        self.locked = bool(active)
        self.pause_tick()

    def _on_show_desktop(self, showing):
        log.info("show desktop: %s", bool(showing))
        self.showing_desktop = bool(showing)
        self.pause_tick()

    # --- géométrie ------------------------------------------------------------------------

    def bbox(self):
        if not self.screens:
            return 0, 0, 1920, 1080
        x0 = min(s["x"] for s in self.screens)
        y0 = min(s["y"] for s in self.screens)
        x1 = max(s["x"] + s["w"] for s in self.screens)
        y1 = max(s["y"] + s["h"] for s in self.screens)
        return x0, y0, x1 - x0, y1 - y0

    def canvas_size(self):
        """Taille de la fenêtre WE = rectangle englobant les écrans allumés. (Au-delà, Wine ne rend
        plus toute la fenêtre : bandes noires.) Réglable à la main dans les réglages avancés."""
        if not self.cfg["canvas_auto"] and all(self.cfg.get("canvas") or [0, 0]):
            return tuple(self.cfg["canvas"])
        _, _, w, h = self.bbox()
        return w, h

    def content_size(self, w, h):
        c = self.cfg["content"].get(f"{w}x{h}")
        return tuple(c) if c else (w, h)

    def target(self):
        x0, y0, bw, _ = self.bbox()
        w, h = self.window_size or self.canvas_size()
        return {"title": WINDOW_TITLE, "x": x0 + bw + 1000, "y": y0, "w": w, "h": h}

    def wallpaper_info(self, wid=None):
        """(type, fichier vidéo) du fond ; le type vient de project.json."""
        pj = steam.wallpaper_path(self.info, wid or self.cfg["wallpaper"])
        if not pj:
            return "", None
        try:
            p = json.loads(pj.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return "", None
        kind = str(p.get("type") or "").lower()
        f = pj.parent / str(p.get("file") or "")
        return kind, (f if kind == "video" and f.is_file() else None)

    def loop_file(self, f):
        """Vidéo courte : version allongée (copiée bout à bout, sans réencodage) si elle est prête.
        Le lecteur marque un petit à-coup à chaque retour au début ; une boucle de 5 s en fait un
        toutes les 5 s, la version longue une fois par minute environ."""
        key = str(f)
        if key not in self.loops:
            self.loops[key] = None

            def run():      # ffmpeg à part : le Worker reste libre pour WE (pause, ouvertures…)
                res = media.extended_loop(f)
                GLib.idle_add(lambda: (self.loops.__setitem__(key, res), res and self.write_state(), False)[-1])
            threading.Thread(target=run, daemon=True).start()
        return self.loops[key] or f

    def video_mode(self):
        """Fond vidéo lu directement par Plasma : décodage GPU, vraie fréquence d'image, et on évite
        le lecteur vidéo de WE sous Proton (saccadé, et il plante quand on enchaîne les vidéos)."""
        return bool(self.cfg.get("native_video", True)) and self.wallpaper_info()[1] is not None

    def next_title(self):
        return f"{WINDOW_TITLE}-b" if self.title == f"{WINDOW_TITLE}-a" else f"{WINDOW_TITLE}-a"

    # --- supervision ----------------------------------------------------------------------

    def tick(self):
        try:
            self._tick()
        except Exception:
            log.exception("tick")
        return True

    def _tick(self):
        now = time.time()
        if not self.video_mode():
            self.video_since = 0.0
        pid = engine.we_pid()
        if not pid:
            self.we_seen_since = 0
            self.xid = None
            if self.paused:
                self.paused = False
            if self.cfg["start_engine"] and not self.user_stopped and self.info.ok and not self.video_mode() \
                    and not self.worker.busy and not self.locked:
                # (session verrouillée : l'interface de Steam ne se dessine plus et reste bloquée avant le
                # lancement ; on attend le déverrouillage)
                if self.steam_launch_at and now - self.steam_launch_at > STEAM_WAIT and not self.direct_tried:
                    # Steam n'a rien lancé (fenêtre en attente d'une réponse…) : on passe par Proton
                    self.direct_tried = True
                    log.warning("Steam did not start Wallpaper Engine within %d s: starting it through Proton",
                                STEAM_WAIT)
                    engine.launch_direct(self.info)
                elif now - self.last_launch > LAUNCH_COOLDOWN and (self.last_launch == 0 or self.cfg["restart_engine"]):
                    self.last_launch = self.steam_launch_at = now
                    self.direct_tried = False
                    engine.launch_via_steam()
        elif self.video_mode():
            self.steam_launch_at = 0.0
            if not self.we_seen_since:
                self.we_seen_since = now
            if self.paused:                           # rien ne doit rester gelé
                engine.freeze(False)
                self.paused = False
            if not self.video_since:
                self.video_since = now
            # le fond vidéo ne passe pas par WE : on le ferme (RAM, CPU), mais pas tout de suite, au
            # cas où l'on repasse sur une scène (relancer WE prend ~30 s)
            if self.cfg["quit_engine_for_video"] and now - self.video_since > VIDEO_QUIT_DELAY \
                    and not self.worker.busy:
                log.info("video wallpaper: closing Wallpaper Engine (not needed)")
                self.last_launch = 0
                self.worker.submit("quit-for-video", engine.quit_engine)
            else:
                wins = engine.canvas_windows()
                if wins and not self.worker.busy and now - self.last_open > 5:
                    info = self.info       # on libère ses fenêtres
                    self.worker.submit("close-scenes", lambda: [engine.close_wallpaper(info, t) for t in wins])
            self.xid = None
        else:
            self.steam_launch_at = 0.0
            if not self.we_seen_since:
                self.we_seen_since = now
            if not self.info.ok or not self.info.proton or not self.info.proton.exists():
                self.info = steam.SteamInfo(self.cfg.get("proton", ""))
            wins = engine.canvas_windows()
            if self.title not in wins and wins and not self.worker.busy and not self.open_pending:
                self.title = sorted(wins)[-1]        # fenêtre créée avant notre démarrage
            self.xid = wins.get(self.title)
            for xid in wins.values():
                if xid not in self.xid_marked and engine.mark_desktop_type(xid):
                    self.xid_marked.add(xid)
            # fenêtres orphelines (ancienne version, fermeture ignorée par WE…) : on les ferme
            stray = [t for t in wins if t != self.title]
            if stray and self.xid and not self.worker.busy and not self.open_pending \
                    and now - self.last_open > 10:
                info = self.info
                self.worker.submit("cleanup", lambda: [engine.close_wallpaper(info, t) for t in stray])
            w, h = self.canvas_size()
            if self.xid is None:
                if now - self.we_seen_since > WE_WARMUP and now - self.last_open > OPEN_COOLDOWN \
                        and not self.worker.busy:
                    self.open_current()
            else:
                if self.window_size is None:
                    self.window_size = desktop.rule_size()   # fenêtre créée avant notre démarrage
                if self.window_size and self.window_size != (w, h) and not self.worker.busy \
                        and now - self.layout_changed > LAYOUT_SETTLE \
                        and (now - self.layout_changed > X_SCREEN_WAIT
                             or desktop.x_screen_size() in (None, (w, h))):
                    log.info("render size %s -> %s: re-creating the window", self.window_size, (w, h))
                    self.open_current(recreate=True)
                elif not self.worker.busy and not self.open_pending:
                    self.verify_tick(now, w, h)
            idx = engine.sink_input() if now - self.last_audio_check > 10 or self.sink_idx is None else self.sink_idx
            if idx is not None:
                self.last_audio_check = now
            if idx is not None and idx != self.sink_idx:
                self.sink_idx = idx
                engine.set_audio(self.cfg["volume"], self.cfg["muted"])
        self.write_state()

    def verify_tick(self, now, w, h):
        """Mesure ce que WE dessine vraiment, et en garde l'image si elle est bonne (le fond Plasma
        l'affiche à l'ouverture de session, avant que WE ait démarré).
        Juste après un changement d'écrans, Wine peut encore avoir l'ancienne disposition : WE
        dessine alors à l'ancienne taille dans un coin de la fenêtre et laisse le reste noir. On
        rouvre alors la fenêtre (délais croissants) tant que ce n'est pas bon."""
        if self.reopen_at and now > self.reopen_at:
            self.reopen_at = 0.0
            self.open_current(recreate=True)
            return
        if not self.verify_at and self.xid and now - self.last_snapshot > SNAPSHOT_EVERY:
            self.verify_at = now
        # (session verrouillée : KWin n'affiche plus la fenêtre de WE, sa capture serait noire)
        if not (self.verify_at and now > self.verify_at and self.xid and not self.paused and not self.locked):
            return
        self.verify_at = 0.0
        self.last_snapshot = now
        xid, wid = self.xid, self.opened_wallpaper or self.cfg["wallpaper"]
        after_layout = now - self.layout_changed < VERIFY_WINDOW
        S.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = S.FRAME_FILE.with_suffix(".tmp.jpg")

        def done(ext):
            if not ext:
                return
            if ext[0] >= w - 24 and ext[1] >= h - 24:
                if self.bad_renders:
                    log.info("render OK at %dx%d after %d re-open(s)", w, h, self.bad_renders)
                self.bad_renders = 0
                if wid == self.cfg["wallpaper"] and tmp.is_file():
                    tmp.replace(S.FRAME_FILE)
                    self.frame = {"wallpaper": wid, "size": [w, h], "time": int(time.time())}
                    self.write_state()
                return
            tmp.unlink(missing_ok=True)
            if not after_layout:
                return          # scène sombre sur un bord, sans doute : on ne garde pas l'image, c'est tout
            if self.bad_renders >= len(REOPEN_DELAYS):
                log.warning("Wallpaper Engine still draws only %dx%d of %dx%d: giving up", *ext, w, h)
                self.bad_renders = 0
                return
            delay = REOPEN_DELAYS[self.bad_renders]
            self.bad_renders += 1
            log.info("Wallpaper Engine draws only %dx%d of %dx%d (old screen layout?): "
                     "re-opening in %ds", *ext, w, h, delay)
            self.reopen_at = time.time() + delay

        self.worker.submit("verify", lambda: engine.drawn_extent(xid, tmp), done)

    def open_current(self, recreate=False):
        # clics rapides : une seule ouverture en attente, qui prendra le dernier fond choisi
        if self.open_pending and not recreate:
            return
        pj = steam.wallpaper_path(self.info, self.cfg["wallpaper"])
        if not pj:
            wps = steam.list_wallpapers(self.info)
            if not wps:
                self.message = "no_wallpaper"
                return
            self.cfg["wallpaper"] = wps[0]["id"]
            pj = steam.wallpaper_path(self.info, self.cfg["wallpaper"])
        self.last_open = time.time()
        w, h = self.canvas_size()
        need_new = recreate or self.window_size not in (None, (w, h)) or not desktop.rule_ok(w, h)
        info = self.info

        self.open_pending = True
        old_title = self.title if self.xid else ""
        new_title = self.next_title()

        def job():
            nonlocal pj
            self.open_pending = False
            pj = steam.wallpaper_path(info, self.cfg["wallpaper"]) or pj
            # réglages personnalisés : WE ouvre une copie (liens) du fond avec vos valeurs par défaut
            wid = self.cfg["wallpaper"]
            pj = overlay.build(info, pj, wid, dict(self.cfg["wallpaper_props"].get(wid) or {}))
            self.opened_wallpaper = self.cfg["wallpaper"]
            if need_new:
                desktop.ensure_rule(w, h)
            if engine.window_xid(new_title):          # reste d'un essai précédent
                engine.close_wallpaper(info, new_title)
                time.sleep(0.5)
            # nouveau fond dans une NOUVELLE fenêtre : l'ancienne reste affichée pendant le chargement,
            # et une fenêtre neuve n'a pas de restes de l'ancien fond
            ok = engine.open_wallpaper(info, pj, w, h, new_title)
            xid = None
            for _ in range(80):
                xid = engine.window_xid(new_title)
                if xid:
                    break
                time.sleep(0.25)
            if xid:
                engine.mark_desktop_type(xid)
                time.sleep(1.2)                         # premières images (décodage vidéo…)
            return ok and bool(xid)

        def done(ok):
            self.last_open = time.time()
            if not ok:
                log.warning("failed to open wallpaper %s", self.cfg["wallpaper"])
                self.tick()
                return
            self.title = new_title
            self.window_size = (w, h)
            self.sink_idx = None
            self.grace_until = time.time() + GRACE_S
            self.verify_at = time.time() + VERIFY_DELAY
            if time.time() - self.layout_changed >= VERIFY_WINDOW:
                self.bad_renders = 0
            log.info("wallpaper %s opened at %dx%d (%s)", self.cfg["wallpaper"], w, h, new_title)
            self.tick()
            self.pause_tick(force=True)
            if old_title and old_title != new_title:
                # laisse le plugin basculer sur le nouveau flux avant de fermer l'ancien
                GLib.timeout_add_seconds(3, lambda: (self.worker.submit(
                    "close-old", lambda: engine.close_wallpaper(info, old_title)), False)[1])

        self.worker.submit("open", job, done)

    # --- pause ----------------------------------------------------------------------------

    def screen_covered(self, s):
        c = self.cfg
        return (c["pause_on_fullscreen"] and s.get("fullscreen")) or \
               (c["pause_on_maximized"] and s.get("maximized")) or \
               (c["pause_on_coverage"] and s.get("cover", 0) >= c["coverage_threshold"])

    def want_pause(self):
        w = self._want_pause()
        # « Reprendre » alors que la pause était automatique : on passe outre jusqu'à ce que la
        # situation change (fenêtres dégagées, puis de nouveau recouvertes)
        if self.resume_override:
            if not w[0]:
                self.resume_override = False
            elif w[1] not in ("manual", "locked"):
                return False, ""
        return w

    def _want_pause(self):
        if self.manual_pause:
            return True, "manual"
        if self.locked and self.cfg["pause_on_lock"]:
            return True, "locked"
        if not self.cfg["pause_enabled"] or self.showing_desktop or not self.screens:
            return False, ""
        if time.time() < self.grace_until:
            return False, ""
        cov = [s for s in self.screens if self.screen_covered(s)]
        hit = len(cov) == len(self.screens) if self.cfg["pause_scope"] == "all" else bool(cov)
        if not hit:
            return False, ""
        s = cov[0]
        kind = "fullscreen" if s.get("fullscreen") and self.cfg["pause_on_fullscreen"] else \
               "maximized" if s.get("maximized") and self.cfg["pause_on_maximized"] else "coverage"
        return True, f"{kind}:{','.join(x['name'] for x in cov)}"

    def pause_tick(self, force=False):
        want, reason = self.want_pause()
        now = time.time()
        if self.video_mode():
            if want and not force and reason not in ("manual", "locked") and want != self.video_paused():
                if not self.want_since:
                    self.want_since = now
                if (now - self.want_since) * 1000 < self.cfg["pause_delay_ms"]:
                    return True
            if want != self.video_paused():
                if want:
                    self.video_paused_pos = now - self.video_epoch
                else:
                    self.video_epoch = now - (self.video_paused_pos or 0)
                    self.video_paused_pos = None
                log.info("video %s (%s)", "paused" if want else "playing", reason or "-")
            self.pause_reason = reason if want else ""
            if not want:
                self.want_since = 0
            self.write_state()
            return True
        pid = engine.we_pid()
        if pid and not self.worker.busy:
            # l'état réel peut avoir changé derrière nous (commande -control externe, SIGCONT…)
            stopped = engine.is_stopped(pid)
            if stopped != self.paused:
                self.paused_since = now if stopped else 0.0
            self.paused = stopped
        if want != self.paused or force:
            if want and not force and reason not in ("manual", "locked"):
                if not self.want_since:
                    self.want_since = now
                if (now - self.want_since) * 1000 < self.cfg["pause_delay_ms"]:
                    return True
            # jamais de gel pendant/juste après une commande : WE la traite encore
            if want and (self.worker.busy or time.time() - engine.last_control < 3):
                return True
            if not self.worker.busy and engine.we_pid() and engine.freeze(want):
                if want != self.paused:
                    log.info("%s (%s)", "paused" if want else "playing", reason or "-")
                    if want:
                        self.paused_since = now
                    elif self.paused_since and now - self.paused_since > LONG_PAUSE and self.xid:
                        # WE gelé longtemps : les minuteries des scènes (horloges, dates…) ne rattrapent
                        # pas le temps perdu. Une ouverture neuve repart à l'heure (double tampon : invisible).
                        log.info("resumed after %d min: re-opening the scene so its clock is right",
                                 (now - self.paused_since) / 60)
                        self.reopen_at = now + 1
                    if not want:
                        self.paused_since = 0.0
                self.paused = want
            self.pause_reason = reason if want else ""
            self.write_state()
        if not want:
            self.want_since = 0
        return True

    def video_paused(self):
        return self.video_paused_pos is not None

    # --- état pour le plugin / l'interface ------------------------------------------------

    def state(self):
        vfile = self.wallpaper_info()[1] if self.cfg.get("native_video", True) else None
        w, h = (self.canvas_size() if vfile else (self.window_size or self.canvas_size()))
        cw, ch = self.content_size(w, h)
        wp = self.cfg["wallpaper"]
        preview = ""
        if self.info.ok and wp:
            pj = steam.wallpaper_path(self.info, wp)
            if pj:
                try:
                    prev = json.loads(pj.read_text(encoding="utf-8-sig")).get("preview", "")
                    preview = str(pj.parent / prev) if prev else ""
                except (OSError, ValueError):
                    pass
        return {
            "uuid": self.uuids.get(self.title, "") if self.xid else "",
            "window": [w, h], "content": [cw, ch],
            "offsets": self.cfg["offsets"],
            "muted": self.cfg["muted"], "volume": self.cfg["volume"],
            "paused": self.video_paused() if vfile else self.paused, "pauseReason": self.pause_reason, "manualPause": self.manual_pause,
            "running": bool(engine.we_pid()), "window_ok": bool(self.xid),
            "wallpaper": wp, "preview": preview,
            "screens": self.screens, "busy": self.worker.busy, "message": self.message,
            "lang": S.language(self.cfg),
            "mode": "video" if vfile else "scene",
            "video": vfile and {"path": str(self.loop_file(vfile)), "orig": str(vfile),
                                "epoch": int(self.video_epoch * 1000),
                                "pausedPos": None if self.video_paused_pos is None else int(self.video_paused_pos * 1000)},
            "audioScreen": self.screens[0]["name"] if self.screens else "",
            "frame": self.frame_state(w, h),
        }

    def frame_state(self, w, h):
        f = self.frame
        if not f or f.get("wallpaper") != self.cfg["wallpaper"] or list(f.get("size") or []) != [w, h]:
            return None
        return {"path": str(S.FRAME_FILE), "time": f.get("time", 0)}

    def persist_state(self, st):
        """Copie durable de ce qu'il faut au fond Plasma pour s'afficher avant le démarrage du
        service (ouverture de session) : dernière image, géométrie, vidéo…"""
        keep = {k: st[k] for k in ("window", "content", "offsets", "muted", "volume", "wallpaper",
                                   "preview", "screens", "lang", "mode", "video", "audioScreen", "frame")}
        keep["frameInfo"] = self.frame
        js = json.dumps(keep, ensure_ascii=False, sort_keys=True)
        if js == self.last_persist:
            return
        self.last_persist = js
        try:
            S.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = S.LAST_STATE_FILE.with_suffix(".tmp")
            tmp.write_text(js)
            tmp.replace(S.LAST_STATE_FILE)
        except OSError:
            pass

    def write_state(self):
        st = self.state()
        js = json.dumps(st, ensure_ascii=False, sort_keys=True)
        if js == self.last_state:
            return
        self.last_state = js
        self.rev += 1
        st["rev"] = self.rev
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False))
        tmp.replace(STATE_FILE)
        self.persist_state(st)

    # --- API DBus : script KWin -----------------------------------------------------------

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="s")
    def WindowTarget(self):
        return json.dumps(self.target())

    @dbus.service.method(DBUS_IFACE, in_signature="sis", out_signature="")
    def ReportWindow(self, uuid, pid, caption):
        caption = str(caption)
        if self.uuids.get(caption) != str(uuid):
            self.uuids[caption] = str(uuid)
            self.write_state()

    @dbus.service.method(DBUS_IFACE, in_signature="s", out_signature="")
    def ReportScreens(self, js):
        try:
            scr = json.loads(js)
        except ValueError:
            return
        if not isinstance(scr, list) or not scr:
            return
        old = self.bbox()[2:]
        self.screens = scr
        if self.bbox()[2:] != old:
            self.layout_changed = time.time()
            log.info("screens: %s", ", ".join(f"{s['name']} {s['w']}x{s['h']}@{s['x']},{s['y']}" for s in scr))
        self.pause_tick()
        self.write_state()

    # --- API DBus : interface / CLI -------------------------------------------------------

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="s")
    def GetState(self):
        st = self.state()
        st["settings"] = self.cfg
        st["steam"] = {"root": str(self.info.root or ""), "we": str(self.info.we_dir or ""),
                       "proton": str(self.info.proton or ""), "ok": self.info.ok}
        return json.dumps(st, ensure_ascii=False)

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="s")
    def ListWallpapers(self):
        return json.dumps(steam.list_wallpapers(self.info), ensure_ascii=False)

    @dbus.service.method(DBUS_IFACE, in_signature="ss", out_signature="b")
    def SetSetting(self, key, value_json):
        key = str(key)
        if key not in S.DEFAULTS:
            return False
        try:
            val = json.loads(value_json)
        except ValueError:
            return False
        old = self.cfg.get(key)
        self.cfg[key] = val
        S.save(self.cfg)
        if key == "fps" and val != old:
            self.apply_fps()
        elif key in ("volume", "muted"):
            engine.set_audio(self.cfg["volume"], self.cfg["muted"])
        elif key in ("canvas_auto", "canvas"):
            self.window_size = None if key == "canvas" else self.window_size
        elif key == "proton":
            self.info = steam.SteamInfo(val or "")
        self.pause_tick()
        self.write_state()
        return True

    @dbus.service.method(DBUS_IFACE, in_signature="s", out_signature="b")
    def SetWallpaper(self, wid):
        if not steam.wallpaper_path(self.info, str(wid)):
            return False
        if str(wid) == self.opened_wallpaper and self.cfg["wallpaper"] == str(wid) and self.xid \
                and not self.open_pending:
            return True        # déjà affiché
        self.cfg["wallpaper"] = str(wid)
        S.save(self.cfg)
        if self.video_mode():
            self.video_epoch, self.video_paused_pos = time.time(), None
            self.opened_wallpaper = str(wid)
            self.grace_until = time.time() + GRACE_S
            log.info("wallpaper %s: video played by Plasma", wid)
            self.pause_tick(force=True)
        elif engine.we_pid():
            self.open_current()
        else:
            self.last_launch = 0       # WE pas lancé (on était en mode vidéo) : on le démarre
            self.tick()
        self.write_state()
        return True

    @dbus.service.method(DBUS_IFACE, in_signature="sss", out_signature="b")
    def SetWallpaperProperty(self, wid, key, value_json):
        """Réglage personnalisable d'un fond : mémorisé, et appliqué tout de suite s'il est affiché."""
        try:
            val = json.loads(value_json)
        except ValueError:
            return False
        wid, key = str(wid), str(key)
        self.cfg["wallpaper_props"].setdefault(wid, {})[key] = val
        S.save(self.cfg)
        if wid == self.cfg["wallpaper"] and self.xid and not self.video_mode():
            # (WE ignore les changements de réglages en mode fenêtre : on rouvre le fond avec les
            # nouvelles valeurs ; double tampon, l'ancien reste affiché pendant le chargement)
            self.open_current()
        self.write_state()
        return True

    @dbus.service.method(DBUS_IFACE, in_signature="s", out_signature="b")
    def ResetWallpaperProperties(self, wid):
        """Retour aux réglages d'origine : on rouvre le fond s'il est affiché (WE repart des valeurs
        de project.json)."""
        if self.cfg["wallpaper_props"].pop(str(wid), None) is None:
            return True
        S.save(self.cfg)
        overlay.remove(self.info, str(wid))
        if str(wid) == self.cfg["wallpaper"] and self.xid and not self.video_mode():
            self.open_current(recreate=True)
        self.write_state()
        return True

    @dbus.service.method(DBUS_IFACE, in_signature="i", out_signature="")
    def SetVolume(self, v):
        self.cfg["volume"] = max(0, min(150, int(v)))
        S.save(self.cfg)
        engine.set_audio(self.cfg["volume"], self.cfg["muted"])
        self.write_state()

    @dbus.service.method(DBUS_IFACE, in_signature="b", out_signature="")
    def SetMuted(self, m):
        self.cfg["muted"] = bool(m)
        S.save(self.cfg)
        engine.set_audio(self.cfg["volume"], self.cfg["muted"])
        self.write_state()

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="b")
    def ToggleMute(self):
        self.SetMuted(not self.cfg["muted"])
        return self.cfg["muted"]

    @dbus.service.method(DBUS_IFACE, in_signature="b", out_signature="")
    def SetPaused(self, p):
        """p=True : pause manuelle. p=False : reprise, même si la pause était automatique."""
        self.manual_pause = bool(p)
        self.resume_override = False
        if not p:
            self.resume_override = self._want_pause()[0]
        self.want_since = 0
        self.pause_tick(force=True)

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="b")
    def TogglePause(self):
        paused = self.video_paused() if self.video_mode() else self.paused
        self.SetPaused(not paused)
        return self.manual_pause

    @dbus.service.method(DBUS_IFACE, in_signature="sii", out_signature="")
    def SetOffset(self, screen, x, y):
        self.cfg["offsets"][str(screen)] = {"x": int(x), "y": int(y)}
        S.save(self.cfg)
        self.write_state()

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="")
    def RestartEngine(self):
        self.user_stopped = False

        def job():
            engine.quit_engine()
            time.sleep(2)
        self.worker.submit("restart", job, lambda _: self._relaunch())

    def _relaunch(self):
        self.window_size = None
        self.last_launch = 0
        self.tick()

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="")
    def StopEngine(self):
        self.user_stopped = True
        self.worker.submit("stop", engine.quit_engine, lambda _: self.tick())

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="")
    def StartEngine(self):
        self.user_stopped = False
        self.last_launch = 0
        self.tick()

    @dbus.service.method(DBUS_IFACE, in_signature="", out_signature="")
    def Quit(self):
        engine.freeze(False)
        GLib.idle_add(loop.quit)

    def apply_fps(self):
        """WE lit sa limite de fps au démarrage et réécrit son fichier en quittant : on l'arrête,
        on modifie config.json, on le relance."""
        fps = int(self.cfg["fps"])
        info = self.info

        def job():
            running = bool(engine.we_pid())
            engine.quit_engine()
            time.sleep(1)
            steam.set_we_fps(info, fps)
            return running

        def done(was_running):
            log.info("fps limit: %s", fps)
            self._relaunch()
        self.worker.submit("fps", job, done)


loop = None


def main():
    global loop
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stderr),
                                  logging.FileHandler(S.LOG_FILE)])
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    if bus.name_has_owner(DBUS_NAME):
        print("WE Span is already running.", file=sys.stderr)
        return 0
    try:
        daemon = Daemon(bus)
    except dbus.exceptions.NameExistsException:
        return 0
    loop = GLib.MainLoop()

    def stop(*_):
        engine.freeze(False)   # ne jamais laisser WE gelé derrière nous
        loop.quit()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, stop)
    log.info("service started (Steam: %s, Proton: %s)", daemon.info.root, daemon.info.proton)
    try:
        loop.run()
    finally:
        engine.freeze(False)
    return 0
