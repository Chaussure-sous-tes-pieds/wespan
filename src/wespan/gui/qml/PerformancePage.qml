import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Performances", "Performance")
    function t(fr, en) { return backend.lang === "fr" ? fr : backend.lang === "en" ? en : backend.translate(en) }
    readonly property var cfg: backend.cfg
    readonly property var st: backend.state

    Kirigami.FormLayout {
        RowLayout {
            Kirigami.FormData.label: page.t("Images par seconde (max) :", "Frame rate limit:")
            QQC2.SpinBox {
                id: fps
                from: 10; to: 240; stepSize: 5; editable: true
                value: page.cfg.fps || 60
            }
            QQC2.Button {
                text: page.t("Appliquer", "Apply")
                icon.name: "dialog-ok-apply"
                enabled: backend.serviceRunning && fps.value !== page.cfg.fps
                onClicked: backend.setSetting("fps", fps.value)
            }
        }
        QQC2.Label {
            opacity: 0.7
            text: page.t("Wallpaper Engine redémarre pour appliquer (une vingtaine de secondes).",
                         "Wallpaper Engine restarts to apply this (about twenty seconds).")
        }

        QQC2.CheckBox {
            Kirigami.FormData.label: page.t("Fonds vidéo :", "Video wallpapers:")
            text: page.t("les lire avec Plasma (recommandé)", "play them with Plasma (recommended)")
            checked: page.cfg.native_video !== false
            onToggled: backend.setSetting("native_video", checked)
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 30
            wrapMode: Text.Wrap
            opacity: 0.7
            text: page.t("Décodage par la carte graphique, vraie fréquence d'image, changement instantané. Le lecteur "
                       + "vidéo de Wallpaper Engine sous Proton est saccadé et plante quand on enchaîne les vidéos. "
                       + "Les scènes, elles, passent toujours par Wallpaper Engine.",
                         "GPU decoding, true frame rate, instant switching. Wallpaper Engine's own video player "
                       + "under Proton stutters and crashes when switching videos. Scenes still go through "
                       + "Wallpaper Engine.")
        }

        Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: page.t("Rendu", "Rendering") }

        QQC2.Label {
            Kirigami.FormData.label: page.t("Taille de rendu :", "Render size:")
            text: page.st.window ? page.st.window[0] + " × " + page.st.window[1]
                                   + (page.cfg.canvas_auto !== false ? page.t("  (auto : tous vos écrans)", "  (auto: all your screens)") : "")
                                 : "—"
        }
        QQC2.CheckBox {
            id: auto
            text: page.t("Automatique (recommandé)", "Automatic (recommended)")
            checked: page.cfg.canvas_auto !== false
            onToggled: backend.setSetting("canvas_auto", checked)
        }
        RowLayout {
            visible: !auto.checked
            Kirigami.FormData.label: page.t("Taille manuelle :", "Manual size:")
            QQC2.SpinBox { id: cw; from: 320; to: 16384; editable: true; value: page.cfg.canvas ? page.cfg.canvas[0] : 1920 }
            QQC2.Label { text: "×" }
            QQC2.SpinBox { id: ch; from: 240; to: 16384; editable: true; value: page.cfg.canvas ? page.cfg.canvas[1] : 1080 }
            QQC2.Button { text: page.t("Appliquer", "Apply"); onClicked: backend.setSetting("canvas", [cw.value, ch.value]) }
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 30
            wrapMode: Text.Wrap
            opacity: 0.7
            text: page.t("Wallpaper Engine tourne dans une fenêtre cachée de cette taille ; Wine ne rend pas au-delà "
                       + "de la taille totale de vos écrans (bandes noires). Un fond conçu en 4K reste plus net.",
                         "Wallpaper Engine runs in a hidden window of this size; Wine won't render beyond the total "
                       + "size of your screens (black bars). Wallpapers made in 4K stay sharper.")
        }

        Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "Wallpaper Engine" }

        RowLayout {
            Kirigami.FormData.label: page.t("État :", "Status:")
            QQC2.Label { text: page.st.running ? page.t("lancé", "running") : page.t("arrêté", "stopped") }
            QQC2.Button {
                icon.name: "view-refresh"; text: page.t("Redémarrer", "Restart")
                enabled: backend.serviceRunning
                onClicked: backend.restartEngine()
            }
            QQC2.Button {
                icon.name: page.st.running ? "media-playback-stop" : "media-playback-start"
                text: page.st.running ? page.t("Arrêter", "Stop") : page.t("Démarrer", "Start")
                enabled: backend.serviceRunning
                onClicked: page.st.running ? backend.stopEngine() : backend.startEngine()
            }
        }
        QQC2.Label {
            Kirigami.FormData.label: "Proton :"
            text: page.st.steam ? page.st.steam.proton : ""
            elide: Text.ElideMiddle
            Layout.maximumWidth: Kirigami.Units.gridUnit * 30
            opacity: 0.8
        }
    }
}
