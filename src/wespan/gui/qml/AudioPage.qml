import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Son", "Sound")
    function t(fr, en) { return backend.lang === "fr" ? fr : backend.lang === "en" ? en : backend.translate(en) }
    readonly property var st: backend.state

    Kirigami.FormLayout {
        QQC2.Switch {
            Kirigami.FormData.label: page.t("Son du fond d'écran :", "Wallpaper sound:")
            text: checked ? page.t("Activé", "On") : page.t("Coupé", "Muted")
            checked: !page.st.muted
            enabled: backend.serviceRunning
            onToggled: backend.setMuted(!checked)
        }
        RowLayout {
            Kirigami.FormData.label: page.t("Volume :", "Volume:")
            enabled: backend.serviceRunning && !page.st.muted
            QQC2.Slider {
                id: vol
                from: 0; to: 150; stepSize: 1
                value: page.st.volume !== undefined ? page.st.volume : 100
                Layout.preferredWidth: Kirigami.Units.gridUnit * 16
                onMoved: backend.setVolume(value)
            }
            QQC2.Label { text: Math.round(vol.value) + " %"; Layout.preferredWidth: Kirigami.Units.gridUnit * 3 }
        }
        Kirigami.Separator { Kirigami.FormData.isSection: true }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 30
            wrapMode: Text.Wrap
            opacity: 0.8
            text: page.t("Raccourcis : clic droit sur le bureau → « Couper le son du fond », ou l'applet Volume de la "
                       + "barre des tâches (onglet Applications → Wallpaper Engine). Le réglage est mémorisé et "
                       + "réappliqué à chaque démarrage. Le son s'arrête aussi pendant les pauses.",
                         "Shortcuts: right-click the desktop → “Mute wallpaper”, or the Volume applet in the panel "
                       + "(Applications tab → Wallpaper Engine). The setting is remembered and re-applied at every "
                       + "start. Sound also stops while the wallpaper is paused.")
        }
    }
}
