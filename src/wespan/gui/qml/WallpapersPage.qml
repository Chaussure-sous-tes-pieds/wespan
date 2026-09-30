import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Fonds d'écran", "Wallpapers")
    function t(fr, en) { return backend.lang === "fr" ? fr : backend.lang === "en" ? en : backend.translate(en) }

    property string search: ""
    property string typeFilter: ""
    property string sortMode: "title"

    readonly property var filtered: {
        const q = search.toLowerCase().trim();
        let l = backend.wallpapers.filter(w =>
            (!typeFilter || w.type === typeFilter) &&
            (!q || w.title.toLowerCase().indexOf(q) !== -1 || w.id.indexOf(q) !== -1 ||
             (w.tags || []).join(" ").toLowerCase().indexOf(q) !== -1));
        if (sortMode === "recent") l.sort((a, b) => b.mtime - a.mtime);
        else l.sort((a, b) => a.title.localeCompare(b.title));
        return l;
    }

    function typeLabel(ty) {
        return ty === "video" ? t("Vidéo", "Video") : ty === "scene" ? t("Scène", "Scene")
             : ty === "web" ? "Web" : ty === "application" ? "Application" : (ty || "?");
    }
    readonly property var risky: ["web", "application"]

    actions: [
        Kirigami.Action {
            text: t("Trouver d'autres fonds", "Find more"); icon.name: "search"
            tooltip: t("Rechercher dans le Steam Workshop", "Search the Steam Workshop")
            onTriggered: applicationWindow().showPage("Search")
        },
        Kirigami.Action {
            text: t("Actualiser", "Refresh"); icon.name: "view-refresh"
            onTriggered: backend.refreshWallpapers()
        }
    ]

    header: QQC2.ToolBar {
        contentItem: RowLayout {
            Kirigami.SearchField {
                Layout.fillWidth: true
                placeholderText: t("Rechercher un fond, un tag…", "Search wallpapers, tags…")
                onTextChanged: page.search = text
            }
            QQC2.ComboBox {
                id: typeBox
                textRole: "label"; valueRole: "value"
                model: [
                    { label: page.t("Tous les types", "All types"), value: "" },
                    { label: page.t("Vidéos", "Videos"), value: "video" },
                    { label: page.t("Scènes", "Scenes"), value: "scene" },
                    { label: "Web", value: "web" },
                    { label: "Applications", value: "application" }
                ]
                onActivated: page.typeFilter = currentValue
            }
            QQC2.ComboBox {
                textRole: "label"; valueRole: "value"
                model: [
                    { label: page.t("Par nom", "By name"), value: "title" },
                    { label: page.t("Plus récents", "Newest"), value: "recent" }
                ]
                onActivated: page.sortMode = currentValue
            }
            QQC2.Label { text: page.filtered.length + " / " + backend.wallpapers.length; opacity: 0.7 }
        }
    }

    GridView {
        id: grid
        model: page.filtered
        readonly property int cols: Math.max(1, Math.floor(width / (Kirigami.Units.gridUnit * 13)))
        cellWidth: Math.floor(width / cols)
        cellHeight: cellWidth * 9 / 16 + Kirigami.Units.gridUnit * 2.6
        keyNavigationEnabled: true

        delegate: Item {
            id: cell
            required property var modelData
            width: grid.cellWidth
            height: grid.cellHeight
            readonly property bool current: modelData.id === backend.state.wallpaper

            QQC2.ItemDelegate {
                id: card
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                highlighted: cell.current
                hoverEnabled: true
                padding: Kirigami.Units.smallSpacing
                onClicked: backend.setWallpaper(cell.modelData.id)
                QQC2.ToolTip.text: cell.modelData.title + "\n" + page.typeLabel(cell.modelData.type) + " · " + cell.modelData.id
                    + (page.risky.indexOf(cell.modelData.type) !== -1
                       ? "\n" + page.t("⚠ Ce type fonctionne mal sous Proton", "⚠ This type often misbehaves under Proton") : "")
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: 700

                contentItem: ColumnLayout {
                    spacing: Kirigami.Units.smallSpacing
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: width * 9 / 16
                        color: "black"
                        radius: Kirigami.Units.cornerRadius
                        clip: true
                        // aperçu animé au survol, image fixe sinon (économise le CPU)
                        AnimatedImage {
                            anchors.fill: parent
                            source: cell.modelData.preview ? "file://" + cell.modelData.preview : ""
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            playing: card.hovered
                            cache: false
                        }
                        Rectangle {
                            anchors { right: parent.right; top: parent.top; margins: Kirigami.Units.smallSpacing }
                            radius: height / 2
                            color: Qt.rgba(0, 0, 0, 0.6)
                            implicitWidth: badge.implicitWidth + Kirigami.Units.largeSpacing
                            implicitHeight: badge.implicitHeight + 2
                            QQC2.Label {
                                id: badge
                                anchors.centerIn: parent
                                color: "white"
                                font: Kirigami.Theme.smallFont
                                text: (page.risky.indexOf(cell.modelData.type) !== -1 ? "⚠ " : "") + page.typeLabel(cell.modelData.type)
                            }
                        }
                        Kirigami.Icon {
                            visible: cell.current
                            source: "checkmark"
                            anchors { left: parent.left; top: parent.top; margins: Kirigami.Units.smallSpacing }
                            implicitWidth: Kirigami.Units.iconSizes.smallMedium; implicitHeight: implicitWidth
                            color: Kirigami.Theme.positiveTextColor
                        }
                    }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: cell.modelData.title
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignHCenter
                        font.bold: cell.current
                        color: cell.current ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor
                    }
                }
            }
        }

        Kirigami.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 4
            visible: grid.count === 0
            icon.name: "preferences-desktop-wallpaper"
            text: backend.wallpapers.length === 0 ? page.t("Aucun fond d'écran trouvé", "No wallpapers found")
                                                  : page.t("Aucun résultat", "No results")
            explanation: backend.wallpapers.length === 0
                ? page.t("Abonnez-vous à des fonds sur le Steam Workshop de Wallpaper Engine.",
                         "Subscribe to wallpapers on the Wallpaper Engine Steam Workshop.") : ""
            helpfulAction: Kirigami.Action {
                enabled: backend.wallpapers.length === 0
                text: page.t("Rechercher dans le Workshop", "Search the Workshop"); icon.name: "search"
                onTriggered: applicationWindow().showPage("Search")
            }
        }
    }
}
