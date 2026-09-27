import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: win
    title: "WE Span"
    width: Kirigami.Units.gridUnit * 62
    height: Kirigami.Units.gridUnit * 42
    minimumWidth: Kirigami.Units.gridUnit * 34
    minimumHeight: Kirigami.Units.gridUnit * 26

    function t(fr, en) { return backend.lang === "fr" ? fr : en }
    readonly property var st: backend.state
    readonly property var cfg: backend.cfg
    property string currentPage: "Wallpapers"

    function currentWallpaper() {
        const id = st.wallpaper;
        const l = backend.wallpapers;
        for (let i = 0; i < l.length; i++) if (l[i].id === id) return l[i];
        return null;
    }

    function pauseText() {
        if (!backend.serviceRunning) return t("Service arrêté", "Service stopped");
        if (!st.running) return st.busy ? t("Démarrage de Wallpaper Engine…", "Starting Wallpaper Engine…")
                                        : t("Wallpaper Engine n'est pas lancé", "Wallpaper Engine is not running");
        if (!st.paused) return t("En lecture", "Playing");
        const r = st.pauseReason || "";
        const k = r.split(":")[0], where = r.split(":")[1] || "";
        const why = k === "manual" ? t("pause manuelle", "paused manually")
                  : k === "locked" ? t("écran verrouillé", "screen locked")
                  : k === "maximized" ? t("fenêtre maximisée", "maximized window")
                  : k === "fullscreen" ? t("application en plein écran", "fullscreen application")
                  : k === "coverage" ? t("écran recouvert", "screen covered") : "";
        return t("En pause", "Paused") + (why ? " — " + why : "") + (where ? " (" + where + ")" : "");
    }

    function showPage(name) {
        if (name === currentPage && pageStack.depth > 0) return;
        currentPage = name;
        pageStack.clear();
        pageStack.push(Qt.resolvedUrl(name + "Page.qml"));
    }

    Connections {
        target: backend
        function onToast(kind) {
            if (kind === "wallpaper") win.showPassiveNotification(win.t("Fond d'écran appliqué", "Wallpaper applied"));
            else if (kind === "restart") win.showPassiveNotification(win.t("Redémarrage de Wallpaper Engine…", "Restarting Wallpaper Engine…"));
        }
    }

    globalDrawer: Kirigami.GlobalDrawer {
        id: drawer
        isMenu: false
        modal: false
        collapsible: true
        collapsed: win.width < Kirigami.Units.gridUnit * 48
        showHeaderWhenCollapsed: true
        header: Kirigami.AbstractApplicationHeader {
            contentItem: RowLayout {
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                Kirigami.Icon { source: "wespan"; fallback: "preferences-desktop-wallpaper"; implicitWidth: Kirigami.Units.iconSizes.medium; implicitHeight: implicitWidth }
                Kirigami.Heading { level: 2; text: "WE Span"; visible: !drawer.collapsed; Layout.fillWidth: true }
            }
        }
        actions: [
            Kirigami.Action { text: win.t("Fonds d'écran", "Wallpapers"); icon.name: "preferences-desktop-wallpaper"; checked: win.currentPage === "Wallpapers"; onTriggered: win.showPage("Wallpapers") },
            Kirigami.Action { text: win.t("Pause automatique", "Auto pause"); icon.name: "media-playback-pause"; checked: win.currentPage === "Playback"; onTriggered: win.showPage("Playback") },
            Kirigami.Action { text: win.t("Son", "Sound"); icon.name: "audio-volume-high"; checked: win.currentPage === "Audio"; onTriggered: win.showPage("Audio") },
            Kirigami.Action { text: win.t("Écrans", "Screens"); icon.name: "video-display"; checked: win.currentPage === "Screens"; onTriggered: win.showPage("Screens") },
            Kirigami.Action { text: win.t("Performances", "Performance"); icon.name: "speedometer"; checked: win.currentPage === "Performance"; onTriggered: win.showPage("Performance") },
            Kirigami.Action { text: win.t("Démarrage", "Startup"); icon.name: "system-run"; checked: win.currentPage === "Startup"; onTriggered: win.showPage("Startup") },
            Kirigami.Action { text: win.t("Diagnostic", "Diagnostics"); icon.name: "tools-report-bug"; checked: win.currentPage === "Diagnostic"; onTriggered: win.showPage("Diagnostic") },
            Kirigami.Action { text: win.t("À propos", "About"); icon.name: "help-about"; checked: win.currentPage === "About"; onTriggered: win.showPage("About") }
        ]
    }

    Component.onCompleted: showPage("Wallpapers")
    visible: typeof startHidden === "undefined" || !startHidden

    // avec l'icône de notification, fermer la fenêtre la réduit (le fond continue de toute façon)
    onClosing: (close) => {
        if (backend.trayEnabled) {
            close.accepted = false;
            win.hide();
        }
    }

    header: Kirigami.InlineMessage {
        visible: !backend.serviceRunning
        type: Kirigami.MessageType.Warning
        position: Kirigami.InlineMessage.Position.Header
        text: win.t("Le service WE Span ne tourne pas : le fond d'écran n'est pas piloté.",
                    "The WE Span service is not running: the wallpaper is not being driven.")
        actions: [
            Kirigami.Action { text: win.t("Démarrer le service", "Start service"); icon.name: "media-playback-start"; onTriggered: backend.startService() },
            Kirigami.Action { text: win.t("Diagnostic", "Diagnostics"); icon.name: "tools-report-bug"; onTriggered: win.showPage("Diagnostic") }
        ]
    }

    // mini-lecteur toujours visible
    footer: QQC2.ToolBar {
        position: QQC2.ToolBar.Footer
        // le menu latéral (non modal) recouvre le bas de la fenêtre : on décale le mini-lecteur
        leftPadding: (drawer.modal ? 0 : drawer.width) + Kirigami.Units.largeSpacing
        rightPadding: Kirigami.Units.largeSpacing
        contentItem: RowLayout {
            spacing: Kirigami.Units.largeSpacing
            Image {
                readonly property var wp: win.currentWallpaper()
                source: wp && wp.preview ? "file://" + wp.preview : ""
                Layout.preferredHeight: Kirigami.Units.gridUnit * 2.2
                Layout.preferredWidth: Layout.preferredHeight * 16 / 9
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                sourceSize.width: 200
                clip: true
            }
            ColumnLayout {
                spacing: 0
                Layout.fillWidth: true
                QQC2.Label {
                    readonly property var wp: win.currentWallpaper()
                    text: wp ? wp.title : "—"
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                QQC2.Label {
                    text: win.pauseText()
                    opacity: 0.75
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            QQC2.ToolButton {
                enabled: backend.serviceRunning && !!win.st.running
                icon.name: win.st.paused ? "media-playback-start" : "media-playback-pause"
                text: win.st.paused ? win.t("Reprendre", "Resume") : win.t("Pause", "Pause")
                display: QQC2.AbstractButton.IconOnly
                QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered; QQC2.ToolTip.delay: 500
                onClicked: backend.setPaused(!win.st.paused)
            }
            QQC2.ToolButton {
                enabled: backend.serviceRunning
                icon.name: win.st.muted ? "audio-volume-muted" : "audio-volume-high"
                text: win.st.muted ? win.t("Remettre le son", "Unmute") : win.t("Couper le son", "Mute")
                display: QQC2.AbstractButton.IconOnly
                QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered; QQC2.ToolTip.delay: 500
                onClicked: backend.setMuted(!win.st.muted)
            }
            QQC2.Slider {
                enabled: backend.serviceRunning && !win.st.muted
                from: 0; to: 100; stepSize: 1
                value: win.st.volume !== undefined ? win.st.volume : 100
                Layout.preferredWidth: Kirigami.Units.gridUnit * 8
                onMoved: backend.setVolume(value)
                QQC2.ToolTip.text: Math.round(value) + " %"; QQC2.ToolTip.visible: pressed || hovered
            }
        }
    }
}
