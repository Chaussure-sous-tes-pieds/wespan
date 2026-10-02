import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Recherche dans le Steam Workshop. S'abonner se fait dans Steam (seul le client peut le faire) :
// on y ouvre la page du fond, Steam le télécharge, et il apparaît ici comme « installé ».
Kirigami.ScrollablePage {
    id: page
    title: t("Rechercher", "Search")
    function t(fr, en) { return backend.lang === "fr" ? fr : backend.lang === "en" ? en : backend.translate(en) }

    property string query: ""
    property string sort: "trend"
    property string kind: ""
    property string rating: "Everyone"
    property int days: 7
    property string genre: ""
    property string resolution: ""
    property bool audioOnly: false
    property bool customOnly: false
    property bool approvedOnly: false
    readonly property var extraTags: [genre, resolution, audioOnly ? "Audio responsive" : "",
                                      customOnly ? "Customizable" : "", approvedOnly ? "Approved" : ""].filter(x => x)
    readonly property var ws: backend.workshop
    readonly property var installed: backend.installedIds

    function run(p) {
        backend.workshopSearchEx(query, sort, p || 1, kind, rating, extraTags, days);
        grid.positionViewAtBeginning();
    }
    Component.onCompleted: if (!ws.items || ws.items.length === 0) run(1)

    function typeLabel(ty) {
        return ty === "video" ? t("Vidéo", "Video") : ty === "scene" ? t("Scène", "Scene")
             : ty === "web" ? "Web" : ty === "application" ? "Application" : (ty || "?");
    }
    function fmtCount(n) {
        return n >= 1e6 ? (n / 1e6).toFixed(1) + " M" : n >= 1e3 ? Math.round(n / 1e3) + " k" : String(n);
    }
    function fmtSize(b) {
        return b >= 1e9 ? (b / 1e9).toFixed(1) + t(" Go", " GB") : Math.max(1, Math.round(b / 1e6)) + t(" Mo", " MB");
    }

    actions: [
        Kirigami.Action {
            text: page.t("Clé API…", "API key…"); icon.name: "password-show-on"
            tooltip: page.t("Clé Steam Web API (facultative)", "Steam Web API key (optional)")
            onTriggered: keyDialog.open()
        },
        Kirigami.Action {
            text: page.t("Workshop", "Workshop"); icon.name: "internet-services"
            tooltip: page.t("Ouvrir le Workshop dans Steam", "Open the Workshop in Steam")
            onTriggered: backend.openWorkshop()
        }
    ]

    header: QQC2.ToolBar {
        contentItem: ColumnLayout {
            RowLayout {
                Kirigami.SearchField {
                    id: field
                    Layout.fillWidth: true
                    placeholderText: page.t("Rechercher dans le Workshop…", "Search the Workshop…")
                    autoAccept: false
                    onAccepted: { page.query = text; page.run(1); }
                    onTextChanged: if (text === "" && page.query !== "") { page.query = ""; page.run(1); }
                }
                QQC2.ComboBox {
                    textRole: "label"; valueRole: "value"
                    model: [
                        { label: page.t("Tous les types", "All types"), value: "" },
                        { label: page.t("Scènes", "Scenes"), value: "Scene" },
                        { label: page.t("Vidéos", "Videos"), value: "Video" },
                        { label: "Web", value: "Web" },
                        { label: "Applications", value: "Application" }
                    ]
                    onActivated: { page.kind = currentValue; page.run(1); }
                }
                QQC2.ComboBox {
                    textRole: "label"; valueRole: "value"
                    model: [
                        { label: page.t("Tendances", "Trending"), value: "trend" },
                        { label: page.t("Les mieux notés", "Top rated"), value: "toprated" },
                        { label: page.t("Les plus abonnés", "Most subscribed"), value: "popular" },
                        { label: page.t("Plus récents", "Most recent"), value: "recent" },
                        { label: page.t("Mis à jour récemment", "Recently updated"), value: "updated" },
                        { label: page.t("Pertinence", "Relevance"), value: "relevance" }
                    ]
                    onActivated: { page.sort = currentValue; page.run(1); }
                }
                QQC2.ComboBox {
                    visible: page.sort === "trend"
                    textRole: "label"; valueRole: "value"
                    model: [
                        { label: page.t("Aujourd'hui", "Today"), value: 1 },
                        { label: page.t("Cette semaine", "This week"), value: 7 },
                        { label: page.t("Ce mois-ci", "This month"), value: 30 },
                        { label: page.t("3 mois", "3 months"), value: 90 },
                        { label: page.t("6 mois", "6 months"), value: 180 },
                        { label: page.t("Cette année", "This year"), value: 365 }
                    ]
                    currentIndex: 1
                    onActivated: { page.days = currentValue; page.run(1); }
                }
                QQC2.ToolButton {
                    id: filterButton
                    icon.name: "view-filter"
                    text: page.extraTags.length ? page.t("Filtres (", "Filters (") + page.extraTags.length + ")" : page.t("Filtres", "Filters")
                    checked: page.extraTags.length > 0
                    onClicked: filterMenu.popup(filterButton, 0, filterButton.height)
                }
                QQC2.ComboBox {
                    textRole: "label"; valueRole: "value"
                    model: [
                        { label: page.t("Tout public", "Everyone"), value: "Everyone" },
                        { label: page.t("Tous les âges", "Any rating"), value: "" },
                        { label: page.t("Discutable", "Questionable"), value: "Questionable" },
                        { label: page.t("Adulte", "Mature"), value: "Mature" }
                    ]
                    onActivated: { page.rating = currentValue; page.run(1); }
                }
            }
            QQC2.Label {
                Layout.fillWidth: true
                opacity: 0.7
                elide: Text.ElideRight
                text: backend.workshopBusy ? page.t("Recherche…", "Searching…")
                    : page.t(page.ws.total.toLocaleString(Qt.locale("fr_FR"), "f", 0) + " fonds · page ",
                             page.ws.total.toLocaleString(Qt.locale("en_US"), "f", 0) + " wallpapers · page ")
                      + page.ws.page + " / " + page.ws.pages
                      + page.t(" · « S'abonner » ouvre Steam, le fond apparaît ici une fois téléchargé",
                               " · “Subscribe” opens Steam; the wallpaper shows up here once downloaded")
            }
        }
    }

    QQC2.Menu {
        id: filterMenu
        QQC2.Menu {
            title: page.t("Genre", "Genre") + (page.genre ? " : " + page.genre : "")
            QQC2.MenuItem { text: page.t("Tous", "Any"); checkable: true; checked: page.genre === ""; onTriggered: { page.genre = ""; page.run(1); } }
            Repeater {
                model: backend.workshopTags.genres
                delegate: QQC2.MenuItem {
                    required property var modelData
                    text: modelData; checkable: true; checked: page.genre === modelData
                    onTriggered: { page.genre = modelData; page.run(1); }
                }
            }
        }
        QQC2.Menu {
            title: page.t("Résolution", "Resolution") + (page.resolution ? " : " + page.resolution : "")
            QQC2.MenuItem { text: page.t("Toutes", "Any"); checkable: true; checked: page.resolution === ""; onTriggered: { page.resolution = ""; page.run(1); } }
            Repeater {
                model: backend.workshopTags.resolutions
                delegate: QQC2.MenuItem {
                    required property var modelData
                    text: modelData; checkable: true; checked: page.resolution === modelData
                    onTriggered: { page.resolution = modelData; page.run(1); }
                }
            }
        }
        QQC2.MenuSeparator {}
        QQC2.MenuItem { text: page.t("Réagit au son", "Audio responsive"); checkable: true; checked: page.audioOnly; onTriggered: { page.audioOnly = checked; page.run(1); } }
        QQC2.MenuItem { text: page.t("Personnalisable", "Customizable"); checkable: true; checked: page.customOnly; onTriggered: { page.customOnly = checked; page.run(1); } }
        QQC2.MenuItem { text: page.t("Approuvés par Wallpaper Engine", "Approved by Wallpaper Engine"); checkable: true; checked: page.approvedOnly; onTriggered: { page.approvedOnly = checked; page.run(1); } }
        QQC2.MenuSeparator {}
        QQC2.MenuItem {
            icon.name: "edit-clear"; text: page.t("Effacer les filtres", "Clear filters")
            enabled: page.extraTags.length > 0
            onTriggered: { page.genre = ""; page.resolution = ""; page.audioOnly = false; page.customOnly = false;
                           page.approvedOnly = false; page.run(1); }
        }
    }

    footer: QQC2.ToolBar {
        visible: page.ws.pages > 1
        contentItem: RowLayout {
            Item { Layout.fillWidth: true }
            QQC2.ToolButton {
                icon.name: "go-previous"; text: page.t("Précédente", "Previous")
                enabled: page.ws.page > 1 && !backend.workshopBusy
                onClicked: page.run(page.ws.page - 1)
            }
            QQC2.Label { text: page.ws.page + " / " + page.ws.pages }
            QQC2.ToolButton {
                icon.name: "go-next"; text: page.t("Suivante", "Next")
                enabled: page.ws.page < page.ws.pages && !backend.workshopBusy
                onClicked: page.run(page.ws.page + 1)
            }
            Item { Layout.fillWidth: true }
        }
    }

    GridView {
        id: grid
        model: page.ws.items || []
        readonly property int cols: Math.max(1, Math.floor(width / (Kirigami.Units.gridUnit * 13)))
        cellWidth: Math.floor(width / cols)
        cellHeight: cellWidth * 9 / 16 + Kirigami.Units.gridUnit * 4.4
        opacity: backend.workshopBusy ? 0.5 : 1

        delegate: Item {
            id: cell
            required property var modelData
            width: grid.cellWidth
            height: grid.cellHeight
            readonly property bool have: page.installed.indexOf(modelData.id) !== -1
            readonly property bool current: modelData.id === backend.state.wallpaper

            QQC2.ItemDelegate {
                id: card
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                highlighted: cell.current
                padding: Kirigami.Units.smallSpacing
                onClicked: cell.have ? backend.setWallpaper(cell.modelData.id) : backend.openWorkshopItem(cell.modelData.id)
                QQC2.ToolTip.text: cell.modelData.title
                    + (cell.modelData.tags.length ? "\n" + cell.modelData.tags.join(", ") : "")
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
                        Image {
                            anchors.fill: parent
                            source: cell.modelData.preview
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
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
                                text: ((cell.modelData.type === "web" || cell.modelData.type === "application") ? "⚠ " : "")
                                      + page.typeLabel(cell.modelData.type)
                            }
                        }
                    }
                    QQC2.Label {
                        Layout.fillWidth: true
                        text: cell.modelData.title
                        elide: Text.ElideRight
                        font.bold: cell.current
                    }
                    RowLayout {
                        QQC2.Label {
                            Layout.fillWidth: true
                            opacity: 0.7
                            font: Kirigami.Theme.smallFont
                            text: page.fmtCount(cell.modelData.subs) + page.t(" abonnés", " subscribers")
                                  + (cell.modelData.size ? " · " + page.fmtSize(cell.modelData.size) : "")
                                  + (cell.modelData.resolution ? " · " + cell.modelData.resolution.replace(" x ", "×") : "")
                            elide: Text.ElideRight
                        }
                        QQC2.Button {
                            visible: !cell.have
                            icon.name: "list-add"
                            text: page.t("S'abonner", "Subscribe")
                            onClicked: backend.openWorkshopItem(cell.modelData.id)
                        }
                        QQC2.Button {
                            visible: cell.have
                            enabled: !cell.current
                            icon.name: cell.current ? "checkmark" : "dialog-ok-apply"
                            text: cell.current ? page.t("Affiché", "Showing") : page.t("Appliquer", "Apply")
                            onClicked: backend.setWallpaper(cell.modelData.id)
                        }
                    }
                }
            }
        }

        QQC2.BusyIndicator {
            anchors.centerIn: parent
            running: backend.workshopBusy
            visible: running
        }

        Kirigami.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 4
            visible: grid.count === 0 && !backend.workshopBusy
            icon.name: backend.workshopError ? "network-disconnect" : "search"
            text: backend.workshopError ? page.t("Le Workshop ne répond pas", "The Workshop is not answering")
                                        : page.t("Aucun résultat", "No results")
            explanation: backend.workshopError
            helpfulAction: Kirigami.Action {
                enabled: !!backend.workshopError
                text: page.t("Réessayer", "Retry"); icon.name: "view-refresh"
                onTriggered: page.run(page.ws.page || 1)
            }
        }
    }

    Kirigami.PromptDialog {
        id: keyDialog
        title: page.t("Clé Steam Web API (facultative)", "Steam Web API key (optional)")
        standardButtons: Kirigami.Dialog.Save | Kirigami.Dialog.Cancel
        onAccepted: { backend.setApiKey(keyField.text); page.run(1); }
        onOpened: keyField.text = backend.cfg.steam_api_key || ""
        ColumnLayout {
            QQC2.Label {
                Layout.fillWidth: true
                Layout.maximumWidth: Kirigami.Units.gridUnit * 26
                wrapMode: Text.Wrap
                text: page.t("La recherche marche sans clé. Avec une clé, WE Span interroge directement l'API de Steam "
                           + "(plus rapide et plus fiable). Elle est gratuite et reste sur votre PC.",
                             "Search works without a key. With one, WE Span queries Steam's API directly (faster "
                           + "and more reliable). It's free and stays on your PC.")
            }
            QQC2.TextField {
                id: keyField
                Layout.fillWidth: true
                placeholderText: page.t("Clé (32 caractères)", "Key (32 characters)")
                echoMode: TextInput.Password
            }
            Kirigami.UrlButton {
                url: "https://steamcommunity.com/dev/apikey"
                text: page.t("Obtenir une clé sur steamcommunity.com", "Get a key on steamcommunity.com")
            }
        }
    }
}
