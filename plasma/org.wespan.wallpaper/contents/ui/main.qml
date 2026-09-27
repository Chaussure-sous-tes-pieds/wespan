/*
 * WE Span — fond d'écran Plasma qui affiche Wallpaper Engine.
 *
 * Wallpaper Engine (Steam/Proton) rend dans une fenêtre cachée hors écran. On affiche son flux
 * vidéo en direct (PipeWire via KWin, comme les miniatures de la barre des tâches) et chaque
 * écran n'en montre que la portion correspondant à sa position : l'image est continue d'un
 * écran à l'autre, et c'est un vrai fond Plasma (curseur, widgets, menu du bureau).
 *
 * L'état (fenêtre, décalages, son…) est écrit par le service WE Span dans
 * $XDG_RUNTIME_DIR/wespan/state.json.
 */
import QtQuick
import QtQuick.Window
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.pipewire as PipeWire
import org.kde.taskmanager as TaskManager
import QtMultimedia

WallpaperItem {
    id: root

    readonly property string wespan: 'W=$(command -v wespan || echo "$HOME/.local/bin/wespan"); "$W"'
    property var st: ({})
    readonly property bool fr: st.lang === "fr"
    function t(frText, enText) { return fr ? frText : enText; }

    // --- géométrie --------------------------------------------------------------------------
    readonly property int winW: st.window ? st.window[0] : 1920
    readonly property int winH: st.window ? st.window[1] : 1080
    readonly property int contW: st.content ? st.content[0] : winW
    readonly property int contH: st.content ? st.content[1] : winH
    readonly property var offsets: st.offsets || ({})

    function offsetOf(name) {
        const o = offsets[name];
        return o ? Qt.point(o.x || 0, o.y || 0) : Qt.point(0, 0);
    }

    // Rectangle englobant les écrans ; zoom commun, juste suffisant pour que chaque écran
    // (décalé) reste dans la zone rendue => continuité entre écrans et jamais de noir.
    property var layout: computeLayout()
    function computeLayout() {
        const s = Qt.application.screens;
        let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
        for (let i = 0; i < s.length; i++) {
            x0 = Math.min(x0, s[i].virtualX); y0 = Math.min(y0, s[i].virtualY);
            x1 = Math.max(x1, s[i].virtualX + s[i].width); y1 = Math.max(y1, s[i].virtualY + s[i].height);
        }
        const bcx = (x0 + x1) / 2, bcy = (y0 + y1) / 2;
        let z = 1;   // jamais sous 1:1 (netteté)
        for (let i = 0; i < s.length; i++) {
            const o = offsetOf(s[i].name);
            const l = s[i].virtualX - o.x - bcx, r = l + s[i].width;
            const tp = s[i].virtualY - o.y - bcy, b = tp + s[i].height;
            z = Math.max(z, Math.abs(l) / (contW / 2), Math.abs(r) / (contW / 2),
                            Math.abs(tp) / (contH / 2), Math.abs(b) / (contH / 2));
        }
        return { bcx: bcx, bcy: bcy, zoom: z };
    }
    function relayout() { layout = computeLayout(); }
    onOffsetsChanged: relayout()
    onContWChanged: relayout()
    onContHChanged: relayout()
    Connections {
        target: Qt.application
        function onScreensChanged() { root.relayout(); root.restartStream(); }
    }

    readonly property point myOffset: offsetOf(Screen.name)
    readonly property real zoomF: layout.zoom
    // position (dans cet écran) du coin haut-gauche de la zone rendue
    readonly property real originX: -contW / 2 * zoomF + layout.bcx + myOffset.x - Screen.virtualX
    readonly property real originY: -contH / 2 * zoomF + layout.bcy + myOffset.y - Screen.virtualY

    Rectangle { anchors.fill: parent; color: "black" }

    Item {
        id: viewport
        anchors.fill: parent
        clip: true

        // Aperçu fixe tant qu'aucun flux n'est là (ouverture de session, WE qui démarre…)
        Image {
            x: root.originX; y: root.originY
            width: root.contW * root.zoomF; height: root.contH * root.zoomF
            source: root.st.preview ? "file://" + root.st.preview : ""
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: false
            visible: !root.videoShowing && !streamA.showing && !streamB.showing && status === Image.Ready
            opacity: 0.85
        }

        // Deux flux qui se relaient : au changement de fond, le nouveau se charge sous l'ancien et
        // on bascule dès qu'il a une image (pas de noir ni de flou entre deux fonds).
        PipeWire.PipeWireSourceItem {
            id: streamA
            readonly property bool showing: visible && ready
            nodeId: requestA.nodeId
            visible: requestA.uuid !== "" && nodeId > 0
            z: root.active === 0 ? 2 : 1
            x: root.originX; y: root.originY
            width: root.winW * root.zoomF; height: root.winH * root.zoomF
            onShowingChanged: root.maybeSwap()
        }
        PipeWire.PipeWireSourceItem {
            id: streamB
            readonly property bool showing: visible && ready
            nodeId: requestB.nodeId
            visible: requestB.uuid !== "" && nodeId > 0
            z: root.active === 1 ? 2 : 1
            x: root.originX; y: root.originY
            width: root.winW * root.zoomF; height: root.winH * root.zoomF
            onShowingChanged: root.maybeSwap()
        }

        // Fond vidéo : lu directement (décodage GPU), même rectangle global que les scènes
        VideoOutput {
            id: videoOut
            visible: root.videoMode
            z: 3
            x: root.originX; y: root.originY
            width: root.contW * root.zoomF; height: root.contH * root.zoomF
            fillMode: VideoOutput.PreserveAspectCrop
        }
    }

    // --- fonds vidéo natifs ----------------------------------------------------------------
    readonly property bool videoMode: st.mode === "video" && !!st.video
    readonly property string videoSource: videoMode ? "file://" + st.video.path : ""
    // une vraie image est arrivée depuis le (re)chargement : l'aperçu flou peut disparaître
    property double lastFrame: 0
    property double loadStart: 0
    readonly property bool videoShowing: videoMode && lastFrame > loadStart
    Connections {
        target: videoOut.videoSink
        function onVideoFrameChanged() { root.lastFrame = Date.now(); }
    }
    onVideoSourceChanged: { loadStart = Date.now(); lastFrame = 0; }
    // Lecteur bloqué (arrive parfois quand la vidéo change pendant que ce bureau est recouvert) :
    // aucune image depuis 4 s alors qu'il devrait jouer => on recharge la vidéo.
    function checkStall() {
        if (!videoMode) return;
        const paused = st.video.pausedPos !== null && st.video.pausedPos !== undefined;
        if (paused) return;
        const since = Date.now() - Math.max(lastFrame, loadStart);
        if (since > 4000) {
            console.warn("WE Span: lecteur vidéo bloqué sur", Screen.name, "- rechargement");
            loadStart = Date.now();
            lastFrame = 0;
            player.stop();
            player.source = "";
            player.source = Qt.binding(() => root.videoSource);
            player.play();
            syncTimer.restart();
        }
    }
    MediaPlayer {
        id: player
        source: root.videoSource
        loops: MediaPlayer.Infinite
        videoOutput: videoOut
        audioOutput: AudioOutput {
            // un seul écran joue le son
            muted: !!root.st.muted || Screen.name !== root.st.audioScreen
            volume: Math.min(1.5, (root.st.volume !== undefined ? root.st.volume : 100) / 100)
        }
        onMediaStatusChanged: if (mediaStatus === MediaPlayer.LoadedMedia) root.syncVideo(true)
    }
    function videoTarget() {
        if (!player.duration) return 0;
        const v = st.video;
        const t = v.pausedPos !== null && v.pausedPos !== undefined ? v.pausedPos : Date.now() - v.epoch;
        return ((t % player.duration) + player.duration) % player.duration;
    }
    // Tous les écrans suivent l'horloge du service : petit écart => on ajuste la vitesse (invisible),
    // gros écart => on saute (rarement). Jamais de saut pendant une pause : un saut n'aboutit qu'au
    // prochain rendu, et un bureau recouvert n'est pas redessiné sous Wayland (les sauts s'empilaient
    // et bloquaient la reprise).
    property double lastSeek: 0
    function syncVideo(start) {
        if (!videoMode || !player.duration) return;
        const paused = st.video.pausedPos !== null && st.video.pausedPos !== undefined;
        if (paused) {
            player.playbackRate = 1;
            if (player.playbackState !== MediaPlayer.PausedState) player.pause();
            return;
        }
        if (player.playbackState !== MediaPlayer.PlayingState) player.play();
        const target = videoTarget();
        let diff = target - player.position;
        if (diff > player.duration / 2) diff -= player.duration;
        if (diff < -player.duration / 2) diff += player.duration;
        const now = Date.now();
        if ((start || Math.abs(diff) > 1500) && now - lastSeek > 5000) {
            lastSeek = now;
            player.setPosition(target);
            player.playbackRate = 1;
        } else {
            player.playbackRate = Math.abs(diff) > 40 ? 1 + Math.max(-0.05, Math.min(0.05, diff / 4000)) : 1;
        }
    }
    Timer {
        id: syncTimer
        interval: 1000
        running: root.videoMode
        repeat: true
        onTriggered: { root.syncVideo(false); root.checkStall(); }
    }
    onVideoModeChanged: if (!videoMode) player.stop()

    TaskManager.ScreencastingRequest { id: requestA; uuid: "" }
    TaskManager.ScreencastingRequest { id: requestB; uuid: "" }

    property int active: 0
    readonly property var activeRequest: active === 0 ? requestA : requestB
    readonly property var activeStream: active === 0 ? streamA : streamB
    readonly property var otherRequest: active === 0 ? requestB : requestA
    readonly property var otherStream: active === 0 ? streamB : streamA

    function wantUuid(u) {
        if (!u) { requestA.uuid = ""; requestB.uuid = ""; return; }
        if (activeRequest.uuid === u || otherRequest.uuid === u) return;
        if (!activeStream.showing) { activeRequest.uuid = u; return; }   // rien à préserver
        otherRequest.uuid = u;                                            // chargement en arrière-plan
        swapTimeout.restart();
    }
    function maybeSwap() {
        if (otherRequest.uuid !== "" && otherRequest.uuid === (st.uuid || "") && otherStream.showing) {
            active = 1 - active;
            releaseOld.restart();
        }
    }
    Timer {   // l'ancien flux reste affiché un instant, puis on le libère
        id: releaseOld
        interval: 1500
        onTriggered: if (root.otherRequest.uuid !== (root.st.uuid || "")) root.otherRequest.uuid = ""
    }
    Timer {   // le nouveau flux tarde : on bascule quand même
        id: swapTimeout
        interval: 8000
        onTriggered: if (root.otherRequest.uuid === (root.st.uuid || "") && !root.otherStream.showing) {
            root.active = 1 - root.active;
            root.otherRequest.uuid = "";
        }
    }

    // --- flux : (re)demande robuste ---------------------------------------------------------
    property int failures: 0
    function restartStream() {
        activeRequest.uuid = "";
        rearm.restart();
    }
    Timer {
        id: rearm
        interval: 400
        onTriggered: root.activeRequest.uuid = root.st.uuid || ""
    }

    // --- état partagé -----------------------------------------------------------------------
    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        property var callbacks: ({})
        onNewData: (source, data) => {
            const cb = callbacks[source];
            delete callbacks[source];
            disconnectSource(source);
            if (cb) cb((data["stdout"] || "").trim());
        }
        function run(cmd, cb) {
            const full = cmd + " #" + Date.now() + Math.random();
            callbacks[full] = cb;
            connectSource(full);
        }
    }
    function wespanCmd(args, cb) { exec.run(root.wespan + " " + args, cb); }

    property bool polling: false
    function poll() {
        if (polling) return;
        polling = true;
        exec.run('cat "$XDG_RUNTIME_DIR/wespan/state.json" 2>/dev/null', out => {
            polling = false;
            let s;
            try { s = JSON.parse(out); } catch (e) { s = null; }
            if (!s) { root.st = ({ lang: root.st.lang }); root.wantUuid(""); return; }
            const wasPaused = root.st.video && root.st.video.pausedPos !== null;
            root.st = s;
            root.wantUuid(s.mode === "video" ? "" : (s.uuid || ""));
            if (s.mode === "video" && s.video && (s.video.pausedPos !== null) !== wasPaused) root.syncVideo(false);
            // flux absent alors que la fenêtre existe : on redemande (écran débranché, KWin…)
            if (s.mode !== "video" && s.uuid && root.activeRequest.uuid === s.uuid && !root.activeStream.showing) {
                root.failures++;
                if (root.failures % 4 === 0) root.restartStream();
            } else {
                root.failures = 0;
            }
        });
    }
    Timer {
        interval: 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.poll()
    }

    contextualActions: [
        PlasmaCore.Action {
            text: root.st.muted ? root.t("Remettre le son du fond", "Unmute wallpaper")
                                : root.t("Couper le son du fond", "Mute wallpaper")
            icon.name: root.st.muted ? "audio-volume-high" : "audio-volume-muted"
            onTriggered: root.wespanCmd("togglemute", () => root.poll())
        },
        PlasmaCore.Action {
            text: root.st.paused ? root.t("Reprendre l'animation", "Resume animation")
                                      : root.t("Mettre le fond en pause", "Pause wallpaper")
            icon.name: root.st.paused ? "media-playback-start" : "media-playback-pause"
            onTriggered: root.wespanCmd("togglepause", () => root.poll())
        },
        PlasmaCore.Action {
            text: root.t("Réglages de WE Span…", "WE Span settings…")
            icon.name: "configure"
            onTriggered: root.wespanCmd("settings")
        }
    ]
}
