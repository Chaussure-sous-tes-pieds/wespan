import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasma5support as P5Support

ColumnLayout {
    id: root
    property bool cfg_Unused

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: (source) => disconnectSource(source)
    }

    Kirigami.Icon {
        Layout.alignment: Qt.AlignHCenter
        source: "preferences-desktop-wallpaper"
        implicitWidth: Kirigami.Units.iconSizes.huge
        implicitHeight: implicitWidth
    }
    QQC2.Label {
        Layout.fillWidth: true
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        text: "Wallpaper Engine (WE Span)\n\n"
            + "Fond d'écran, son, pause automatique, alignement des écrans, fps…\n"
            + "Everything is configured in the WE Span app."
    }
    QQC2.Button {
        Layout.alignment: Qt.AlignHCenter
        icon.name: "configure"
        text: "Ouvrir WE Span / Open WE Span"
        onClicked: exec.connectSource('W=$(command -v wespan || echo "$HOME/.local/bin/wespan"); "$W" settings #' + Date.now())
    }
    Item { Layout.fillHeight: true }
}
