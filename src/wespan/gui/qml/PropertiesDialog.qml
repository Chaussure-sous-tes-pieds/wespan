import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtQuick.Dialogs
import org.kde.kirigami as Kirigami

// Réglages personnalisables d'un fond (comme dans Wallpaper Engine). Chaque changement est mémorisé
// et appliqué tout de suite si le fond est affiché (sinon, à sa prochaine ouverture).
Kirigami.Dialog {
    id: dlg
    function t(fr, en) { return backend.lang === "fr" ? fr : backend.lang === "en" ? en : backend.translate(en) }
    property var w: ({})
    property var items: []
    readonly property bool isCurrent: w.id === backend.state.wallpaper
    readonly property bool isVideo: w.type === "video" && backend.cfg.native_video !== false

    title: t("Personnaliser : ", "Customize: ") + (w.title || "")
    preferredWidth: Kirigami.Units.gridUnit * 30
    preferredHeight: Kirigami.Units.gridUnit * 32
    standardButtons: Kirigami.Dialog.Close
    padding: Kirigami.Units.largeSpacing

    function openFor(wp) { w = wp; reload(); open(); }
    function reload() { items = w.id ? backend.wallpaperProperties(w.id) : []; }
    function set(key, value) { backend.setWallpaperProperty(w.id, key, value); reload(); }
    Connections { target: backend; function onLibraryChanged() { if (dlg.visible) dlg.reload(); } }

    customFooterActions: [
        Kirigami.Action {
            text: dlg.t("Réglages d'origine", "Reset to defaults"); icon.name: "edit-undo"
            enabled: dlg.items.some(i => i.custom)
            onTriggered: { backend.resetWallpaperProperties(dlg.w.id); dlg.reload(); }
        }
    ]

    ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: !dlg.isCurrent || dlg.isVideo
            type: Kirigami.MessageType.Information
            text: dlg.isVideo
                ? dlg.t("Ce fond vidéo est lu par Plasma : ces réglages ne s'appliquent que s'il passe par Wallpaper Engine (Performances → décocher « les lire avec Plasma »).",
                        "This video is played by Plasma: these settings only apply when it goes through Wallpaper Engine (Performance → untick “play them with Plasma”).")
                : dlg.t("Ce fond n'est pas affiché : les réglages seront appliqués à sa prochaine ouverture.",
                        "This wallpaper isn't showing: settings will apply next time it's opened.")
        }

        Repeater {
            model: dlg.items
            delegate: Loader {
                required property var modelData
                Layout.fillWidth: true
                visible: modelData.visible
                sourceComponent: modelData.type === "group" ? groupC
                               : modelData.type === "text" ? textC
                               : modelData.type === "bool" ? boolC
                               : modelData.type === "slider" ? sliderC
                               : modelData.type === "combo" ? comboC
                               : modelData.type === "color" ? colorC
                               : modelData.type === "textinput" ? inputC : null
                property var p: modelData
            }
        }
        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            visible: dlg.items.length === 0
            text: dlg.t("Aucun réglage personnalisable", "Nothing to customize")
        }
    }

    Component {
        id: groupC
        Kirigami.Heading { property var p: parent ? parent.p : ({}); level: 4; text: p.label; wrapMode: Text.Wrap; topPadding: Kirigami.Units.largeSpacing }
    }
    Component {
        id: textC
        QQC2.Label { property var p: parent ? parent.p : ({}); text: p.label; wrapMode: Text.Wrap; opacity: 0.75; font: Kirigami.Theme.smallFont; textFormat: Text.PlainText }
    }
    Component {
        id: boolC
        QQC2.CheckBox {
            property var p: parent ? parent.p : ({})
            text: p.label
            checked: p.value === true || p.value === 1 || p.value === "1" || p.value === "true"
            onToggled: dlg.set(p.key, checked)
            font.bold: p.custom
        }
    }
    Component {
        id: sliderC
        ColumnLayout {
            spacing: 0
            property var p: parent ? parent.p : ({})
            RowLayout {
            property var p: parent ? parent.p : ({})
                QQC2.Label { text: p.label; Layout.fillWidth: true; wrapMode: Text.Wrap; font.bold: p.custom }
                QQC2.Label { text: Number(slider.value).toFixed(p.precision); opacity: 0.7 }
            }
            QQC2.Slider {
                id: slider
                Layout.fillWidth: true
                from: p.min; to: p.max; stepSize: p.step
                value: Number(p.value)
                // chaque application passe par une commande à Wallpaper Engine : au relâchement seulement
                onPressedChanged: if (!pressed && Number(value) !== Number(p.value))
                    dlg.set(p.key, p.precision > 0 ? Number(value.toFixed(p.precision)) : Math.round(value))
            }
        }
    }
    Component {
        id: comboC
        RowLayout {
            property var p: parent ? parent.p : ({})
            QQC2.Label { text: p.label; Layout.fillWidth: true; wrapMode: Text.Wrap; font.bold: p.custom }
            QQC2.ComboBox {
                textRole: "label"
                model: p.options
                currentIndex: {
                    for (let i = 0; i < p.options.length; i++) if (String(p.options[i].value) === String(p.value)) return i;
                    return -1;
                }
                onActivated: (i) => dlg.set(p.key, p.options[i].value)
            }
        }
    }
    Component {
        id: colorC
        RowLayout {
            property var p: parent ? parent.p : ({})
            QQC2.Label { text: p.label; Layout.fillWidth: true; wrapMode: Text.Wrap; font.bold: p.custom }
            QQC2.Button {
                implicitWidth: Kirigami.Units.gridUnit * 4
                contentItem: Rectangle { color: p.hex; radius: Kirigami.Units.cornerRadius; border.color: Kirigami.Theme.textColor; border.width: 1 }
                onClicked: colorDialog.open()
                ColorDialog {
                    id: colorDialog
                    selectedColor: p.hex
                    onAccepted: dlg.set(p.key, String(selectedColor).slice(0, 7))
                }
            }
        }
    }
    Component {
        id: inputC
        RowLayout {
            property var p: parent ? parent.p : ({})
            QQC2.Label { text: p.label; Layout.fillWidth: true; wrapMode: Text.Wrap; font.bold: p.custom }
            QQC2.TextField {
                text: p.value === undefined || p.value === null ? "" : String(p.value)
                onEditingFinished: if (text !== String(p.value)) dlg.set(p.key, text)
            }
        }
    }
}
