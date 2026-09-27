import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Pause automatique", "Auto pause")
    function t(fr, en) { return backend.lang === "fr" ? fr : en }
    readonly property var cfg: backend.cfg
    readonly property var st: backend.state

    function covered(s) {
        return (cfg.pause_on_fullscreen && s.fullscreen) || (cfg.pause_on_maximized && s.maximized) ||
               (cfg.pause_on_coverage && s.cover >= cfg.coverage_threshold);
    }

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: true
            type: Kirigami.MessageType.Information
            text: page.t("En pause, le fond n'est pas retiré : l'image reste affichée, figée, et Wallpaper Engine "
                       + "n'utilise plus ni processeur ni carte graphique.",
                         "When paused the wallpaper is not removed: the last frame stays on screen, frozen, and "
                       + "Wallpaper Engine uses no CPU or GPU at all.")
        }

        Kirigami.FormLayout {
            Layout.fillWidth: true

            QQC2.Switch {
                Kirigami.FormData.label: page.t("Pause automatique :", "Auto pause:")
                text: checked ? page.t("Activée", "Enabled") : page.t("Désactivée", "Disabled")
                checked: !!page.cfg.pause_enabled
                onToggled: backend.setSetting("pause_enabled", checked)
            }

            Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: page.t("Un écran est « couvert » quand…", "A screen counts as “covered” when…") }

            QQC2.CheckBox {
                enabled: !!page.cfg.pause_enabled
                text: page.t("une fenêtre y est maximisée", "a window is maximized on it")
                checked: !!page.cfg.pause_on_maximized
                onToggled: backend.setSetting("pause_on_maximized", checked)
            }
            QQC2.CheckBox {
                enabled: !!page.cfg.pause_enabled
                text: page.t("une application y est en plein écran (jeu, vidéo…)", "an application is fullscreen on it (game, video…)")
                checked: !!page.cfg.pause_on_fullscreen
                onToggled: backend.setSetting("pause_on_fullscreen", checked)
            }
            RowLayout {
                enabled: !!page.cfg.pause_enabled
                QQC2.CheckBox {
                    id: covBox
                    text: page.t("les fenêtres en recouvrent au moins", "windows cover at least")
                    checked: !!page.cfg.pause_on_coverage
                    onToggled: backend.setSetting("pause_on_coverage", checked)
                }
                QQC2.Slider {
                    id: thr
                    enabled: covBox.checked
                    from: 30; to: 100; stepSize: 5
                    value: page.cfg.coverage_threshold || 90
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 10
                    onMoved: backend.setSetting("coverage_threshold", Math.round(value))
                }
                QQC2.Label { text: Math.round(thr.value) + " %"; enabled: covBox.checked }
            }

            Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: page.t("Mettre en pause…", "Pause…") }

            QQC2.RadioButton {
                enabled: !!page.cfg.pause_enabled
                text: page.t("quand tous les écrans sont couverts (le fond n'est plus visible nulle part)",
                             "when every screen is covered (the wallpaper is visible nowhere)")
                checked: page.cfg.pause_scope !== "any"
                onToggled: if (checked) backend.setSetting("pause_scope", "all")
            }
            QQC2.RadioButton {
                enabled: !!page.cfg.pause_enabled
                text: page.t("dès qu'un écran est couvert", "as soon as one screen is covered")
                checked: page.cfg.pause_scope === "any"
                onToggled: if (checked) backend.setSetting("pause_scope", "any")
            }

            Kirigami.Separator { Kirigami.FormData.isSection: true }

            QQC2.CheckBox {
                Kirigami.FormData.label: page.t("Aussi :", "Also:")
                text: page.t("mettre en pause quand l'écran est verrouillé", "pause while the screen is locked")
                checked: !!page.cfg.pause_on_lock
                onToggled: backend.setSetting("pause_on_lock", checked)
            }
            RowLayout {
                Kirigami.FormData.label: page.t("Délai avant la pause :", "Delay before pausing:")
                QQC2.SpinBox {
                    from: 0; to: 10000; stepSize: 100; editable: true
                    value: page.cfg.pause_delay_ms !== undefined ? page.cfg.pause_delay_ms : 800
                    onValueModified: backend.setSetting("pause_delay_ms", value)
                }
                QQC2.Label { text: "ms"; opacity: 0.7 }
            }
            QQC2.Label {
                text: page.t("« Afficher le bureau » (Win+D) relance toujours l'animation.",
                             "“Show Desktop” (Meta+D) always resumes the animation.")
                opacity: 0.7
            }
        }

        Kirigami.Heading { level: 3; text: page.t("En ce moment", "Right now") }

        RowLayout {
            Layout.fillWidth: true
            Kirigami.Icon {
                source: page.st.paused ? "media-playback-pause" : "media-playback-start"
                implicitWidth: Kirigami.Units.iconSizes.medium; implicitHeight: implicitWidth
            }
            QQC2.Label { text: applicationWindow().pauseText(); font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
            QQC2.Button {
                enabled: backend.serviceRunning
                icon.name: page.st.paused ? "media-playback-start" : "media-playback-pause"
                text: page.st.paused ? page.t("Reprendre", "Resume") : page.t("Mettre en pause", "Pause now")
                onClicked: backend.setPaused(!page.st.paused)
            }
        }

        Repeater {
            model: page.st.screens || []
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    source: page.covered(modelData) ? "dialog-ok" : "video-display"
                    implicitWidth: Kirigami.Units.iconSizes.smallMedium; implicitHeight: implicitWidth
                }
                QQC2.Label { text: modelData.name + "  " + modelData.w + "×" + modelData.h; Layout.preferredWidth: Kirigami.Units.gridUnit * 10 }
                QQC2.ProgressBar { from: 0; to: 100; value: modelData.cover; Layout.fillWidth: true }
                QQC2.Label { text: Math.round(modelData.cover) + " %"; Layout.preferredWidth: Kirigami.Units.gridUnit * 3 }
                QQC2.Label {
                    text: (modelData.fullscreen ? page.t("plein écran", "fullscreen") : modelData.maximized ? page.t("maximisée", "maximized") : "")
                        + (page.covered(modelData) ? "  → " + page.t("couvert", "covered") : "")
                    opacity: 0.8
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 9
                }
            }
        }
    }
}
