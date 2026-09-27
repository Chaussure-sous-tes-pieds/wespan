import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Diagnostic", "Diagnostics")
    function t(fr, en) { return backend.lang === "fr" ? fr : en }
    readonly property var problems: backend.diagnostics.filter(d => !d.ok)
    property string log: ""
    Component.onCompleted: { backend.refreshDiagnostics(); log = backend.logTail() }

    actions: [
        Kirigami.Action {
            text: page.t("Tout réparer", "Fix everything"); icon.name: "tools-wizard"
            enabled: page.problems.length > 0 && !backend.busy
            onTriggered: backend.fix("all")
        },
        Kirigami.Action {
            text: page.t("Actualiser", "Refresh"); icon.name: "view-refresh"
            onTriggered: { backend.refreshDiagnostics(); page.log = backend.logTail() }
        }
    ]

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: true
            type: page.problems.length ? Kirigami.MessageType.Warning : Kirigami.MessageType.Positive
            text: backend.busy ? page.t("Réparation en cours…", "Fixing…")
                : page.problems.length ? page.t(page.problems.length + " point(s) à corriger.", page.problems.length + " issue(s) found.")
                                       : page.t("Tout est en ordre.", "Everything looks good.")
        }
        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: page.problems.some(p => p.id === "steam_option")
            type: Kirigami.MessageType.Information
            text: page.t("Réparer l'option de lancement ferme Steam quelques secondes puis le relance (Steam réécrit "
                       + "sa configuration en quittant).",
                         "Fixing the launch option closes Steam for a few seconds and restarts it (Steam rewrites its "
                       + "configuration when it quits).")
        }

        Repeater {
            model: backend.diagnostics
            delegate: RowLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon {
                    source: modelData.ok ? "dialog-ok" : "dialog-error"
                    color: modelData.ok ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.negativeTextColor
                    implicitWidth: Kirigami.Units.iconSizes.smallMedium; implicitHeight: implicitWidth
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    QQC2.Label { text: backend.lang === "fr" ? modelData.label_fr : modelData.label_en; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    QQC2.Label {
                        visible: !!modelData.detail
                        text: modelData.detail || ""
                        opacity: 0.6
                        font: Kirigami.Theme.smallFont
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                }
                QQC2.Button {
                    visible: !modelData.ok && !!modelData.fix
                    enabled: !backend.busy
                    icon.name: "tools-wizard"
                    text: backend.busy === modelData.fix ? page.t("En cours…", "Working…") : page.t("Réparer", "Fix")
                    onClicked: backend.fix(modelData.fix)
                }
            }
        }

        Kirigami.Heading { level: 3; text: page.t("Journal", "Log") }
        QQC2.TextArea {
            Layout.fillWidth: true
            Layout.preferredHeight: Kirigami.Units.gridUnit * 14
            readOnly: true
            wrapMode: Text.NoWrap
            font.family: "monospace"
            font.pointSize: Kirigami.Theme.smallFont.pointSize > 0 ? Kirigami.Theme.smallFont.pointSize : 8
            text: page.log
        }
        RowLayout {
            QQC2.Button {
                icon.name: "folder-open"; text: page.t("Ouvrir le dossier du journal", "Open log folder")
                onClicked: backend.openFolder(backend.logDir())
            }
            QQC2.Button {
                icon.name: "edit-copy"; text: page.t("Copier (pour un rapport de bug)", "Copy (for a bug report)")
                onClicked: { logCopy.text = page.log; logCopy.selectAll(); logCopy.copy() }
            }
            TextEdit { id: logCopy; visible: false }
        }
    }
}
