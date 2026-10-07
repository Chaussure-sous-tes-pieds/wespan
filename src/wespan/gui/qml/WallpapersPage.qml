import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtCore
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Fonds d'écran", "Wallpapers")
    function t(fr, en) { return backend.lang === "fr" ? fr : backend.lang === "en" ? en : backend.translate(en) }

    // --- état de la vue (tri, filtres, dossier) ; les principaux sont gardés d'une fois sur l'autre
    property string search: ""
    property string typeFilter: ""
    property string sortMode: "title"
    property bool sortDesc: false
    property string folder: ""            // "" = tous, "__fav" = favoris, sinon nom du dossier
    property string ratingFilter: ""
    property string resFilter: ""
    property string tagFilter: ""
    property string sourceFilter: ""
    property bool audioOnly: false
    property bool customOnly: false
    property bool approvedOnly: false
    Settings {
        category: "library"
        property alias sortMode: page.sortMode
        property alias sortDesc: page.sortDesc
        property alias folder: page.folder
        property alias typeFilter: page.typeFilter
        property alias ratingFilter: page.ratingFilter
    }

    // tri mémorisé qui n'est plus proposé (note sans clé API…) : retour au nom
    readonly property string effectiveSort: sortMode === "score" && !haveScores ? "title" : sortMode
    readonly property var favs: backend.favorites
    readonly property var folderList: backend.folders
    readonly property int extraFilters: (ratingFilter ? 1 : 0) + (resFilter ? 1 : 0) + (tagFilter ? 1 : 0)
        + (sourceFilter ? 1 : 0) + (audioOnly ? 1 : 0) + (customOnly ? 1 : 0) + (approvedOnly ? 1 : 0)

    function folderOf(id) {
        for (let i = 0; i < folderList.length; i++)
            if ((folderList[i].ids || []).indexOf(id) !== -1) return folderList[i].name;
        return "";
    }
    // dossiers exclus de « Tous »
    readonly property var hiddenIds: {
        let ids = [];
        folderList.forEach(f => { if (f.hidden) ids = ids.concat(f.ids || []); });
        return ids;
    }
    function inFolder(w) {
        if (folder === "") return hiddenIds.indexOf(w.id) === -1;
        if (folder === "__fav") return favs.indexOf(w.id) !== -1;
        return folderOf(w.id) === folder;
    }
    function countIn(name) {
        if (name === "") return backend.wallpapers.filter(w => hiddenIds.indexOf(w.id) === -1).length;
        if (name === "__fav") return backend.wallpapers.filter(w => favs.indexOf(w.id) !== -1).length;
        for (let i = 0; i < folderList.length; i++)
            if (folderList[i].name === name)
                return backend.wallpapers.filter(w => (folderList[i].ids || []).indexOf(w.id) !== -1).length;
        return 0;
    }
    // glisser-déposer d'un fond sur un dossier : on cherche nous-mêmes le dossier sous le pointeur
    property var chips: []
    property var dropChip: null           // dossier sous le pointeur pendant un glisser
    function chipAt(item, x, y) {
        const p = item.mapToItem(null, x, y);
        for (let i = 0; i < chips.length; i++) {
            const c = chips[i];
            if (!c || !c.visible) continue;
            const q = c.mapFromItem(null, p.x, p.y);
            if (q.x >= 0 && q.y >= 0 && q.x <= c.width && q.y <= c.height) return c;
        }
        return null;
    }
    function dropOn(chip, id) {
        if (!chip || !id) return;
        if (chip.name === "__fav") { if (favs.indexOf(id) === -1) backend.toggleFavorite(id); }
        else if (chip.name !== "") backend.moveToFolder(id, chip.name);
        else backend.moveToFolder(id, "");          // « Tous » : sortir du dossier
    }

    function allTags(w) { return (w.tags || []).concat(w.wsTags || []); }

    // valeurs présentes dans la bibliothèque (menus de filtres)
    readonly property var presentRes: {
        const s = {};
        backend.wallpapers.forEach(w => { if (w.resolution) s[w.resolution] = 1; });
        return Object.keys(s).sort((a, b) => (parseInt(b) || 0) - (parseInt(a) || 0));
    }
    readonly property var presentTags: {
        const s = {};
        backend.wallpapers.forEach(w => allTags(w).forEach(tg => {
            if (tg && tg !== "Customizable" && tg !== "Audio responsive") s[tg] = 1;
        }));
        return Object.keys(s).sort();
    }
    readonly property bool haveScores: backend.wallpapers.some(w => (w.score || 0) > 0)

    readonly property var filtered: {
        const q = search.toLowerCase().trim();
        let l = backend.wallpapers.filter(w =>
            inFolder(w) &&
            (!typeFilter || w.type === typeFilter) &&
            (!ratingFilter || w.rating === ratingFilter) &&
            (!resFilter || w.resolution === resFilter) &&
            (!tagFilter || allTags(w).indexOf(tagFilter) !== -1) &&
            (!sourceFilter || w.source === sourceFilter) &&
            (!audioOnly || w.audio) && (!customOnly || w.customizable) && (!approvedOnly || w.approved) &&
            (!q || w.title.toLowerCase().indexOf(q) !== -1 || w.id.indexOf(q) !== -1 ||
             allTags(w).join(" ").toLowerCase().indexOf(q) !== -1));
        const num = { added: 1, updated: 1, size: 1, subs: 1, favorited: 1, score: 1 };
        const dir = sortDesc ? -1 : 1;
        l.sort((a, b) => {
            let c = 0;
            if (effectiveSort === "type") c = (a.type || "").localeCompare(b.type || "");
            else if (num[effectiveSort]) c = (a[effectiveSort] || 0) - (b[effectiveSort] || 0);
            else c = a.title.localeCompare(b.title);
            return c !== 0 ? c * dir : a.title.localeCompare(b.title);
        });
        // favoris en tête (comme Wallpaper Engine), sauf dans la vue Favoris
        if (folder !== "__fav") {
            const f = l.filter(w => favs.indexOf(w.id) !== -1);
            l = f.concat(l.filter(w => favs.indexOf(w.id) === -1));
        }
        return l;
    }

    function typeLabel(ty) {
        return ty === "video" ? t("Vidéo", "Video") : ty === "scene" ? t("Scène", "Scene")
             : ty === "web" ? "Web" : ty === "application" ? "Application" : (ty || "?");
    }
    function fmtSize(b) {
        return b >= 1e9 ? (b / 1e9).toFixed(1) + t(" Go", " GB") : Math.max(1, Math.round(b / 1e6)) + t(" Mo", " MB");
    }
    readonly property var risky: ["web", "application"]
    readonly property var sorts: [
        { label: t("Nom", "Name"), value: "title", desc: false },
        { label: t("Date d'ajout", "Date added"), value: "added", desc: true },
        { label: t("Dernière mise à jour", "Last updated"), value: "updated", desc: true },
        { label: t("Popularité (abonnés)", "Popularity (subscribers)"), value: "subs", desc: true },
        { label: t("Favoris sur le Workshop", "Workshop favorites"), value: "favorited", desc: true },
        { label: t("Note", "Rating"), value: "score", desc: true },
        { label: t("Taille", "Size"), value: "size", desc: true },
        { label: t("Type", "Type"), value: "type", desc: false }
    ]

    actions: [
        Kirigami.Action {
            text: t("Trouver d'autres fonds", "Find more"); icon.name: "search"
            tooltip: t("Rechercher dans le Steam Workshop", "Search the Steam Workshop")
            onTriggered: applicationWindow().showPage("Search")
        },
        Kirigami.Action {
            text: t("Actualiser la liste", "Refresh list"); icon.name: "view-refresh"
            onTriggered: backend.refreshWallpapers()
        }
    ]

    header: QQC2.ToolBar {
        contentItem: ColumnLayout {
            spacing: Kirigami.Units.smallSpacing
            RowLayout {
                Kirigami.SearchField {
                    Layout.fillWidth: true
                    placeholderText: page.t("Rechercher un fond, un tag…", "Search wallpapers, tags…")
                    onTextChanged: page.search = text
                }
                QQC2.ComboBox {
                    textRole: "label"; valueRole: "value"
                    model: [
                        { label: page.t("Tous les types", "All types"), value: "" },
                        { label: page.t("Vidéos", "Videos"), value: "video" },
                        { label: page.t("Scènes", "Scenes"), value: "scene" },
                        { label: "Web", value: "web" },
                        { label: "Applications", value: "application" }
                    ]
                    Component.onCompleted: currentIndex = Math.max(0, indexOfValue(page.typeFilter))
                    onActivated: page.typeFilter = currentValue
                }
                QQC2.ComboBox {
                    textRole: "label"; valueRole: "value"
                    model: page.sorts.filter(s => s.value !== "score" || page.haveScores)
                    // (le modèle change quand la langue change ou que les notes arrivent : on resynchronise)
                    currentIndex: Math.max(0, model.findIndex(s => s.value === page.sortMode))
                    onActivated: { page.sortMode = currentValue; page.sortDesc = model[currentIndex].desc; }
                }
                QQC2.ToolButton {
                    icon.name: page.sortDesc ? "view-sort-descending" : "view-sort-ascending"
                    display: QQC2.AbstractButton.IconOnly
                    text: page.sortDesc ? page.t("Ordre décroissant", "Descending") : page.t("Ordre croissant", "Ascending")
                    QQC2.ToolTip.text: text; QQC2.ToolTip.visible: hovered; QQC2.ToolTip.delay: 500
                    onClicked: page.sortDesc = !page.sortDesc
                }
                QQC2.ToolButton {
                    id: filterButton
                    icon.name: "view-filter"
                    text: page.extraFilters ? page.t("Filtres (", "Filters (") + page.extraFilters + ")" : page.t("Filtres", "Filters")
                    checked: page.extraFilters > 0
                    onClicked: filterMenu.popup(filterButton, 0, filterButton.height)
                }
                QQC2.Label { text: page.filtered.length + " / " + backend.wallpapers.length; opacity: 0.7 }
            }
            // dossiers (clic droit sur un dossier : renommer, déplacer, supprimer)
            Flow {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing
                FolderChip { name: ""; label: page.t("Tous", "All"); iconName: "view-list-icons" }
                FolderChip { name: "__fav"; label: page.t("Favoris", "Favorites"); iconName: "starred-symbolic" }
                Repeater {
                    model: page.folderList
                    delegate: FolderChip {
                        required property var modelData
                        name: modelData.name; label: modelData.name; editable: true
                        iconName: modelData.hidden ? "view-hidden" : "folder"
                        QQC2.ToolTip.text: modelData.hidden ? page.t("Masqué dans « Tous »", "Hidden from “All”") : ""
                        QQC2.ToolTip.visible: hovered && !!modelData.hidden
                    }
                }
                QQC2.ToolButton {
                    icon.name: "folder-new"
                    text: page.t("Nouveau dossier", "New folder")
                    onClicked: { nameDialog.mode = "new"; nameDialog.wid = ""; nameDialog.open(); }
                }
            }
        }
    }

    component CardButton: Rectangle {
        id: cb
        property string iconName
        property color tint: "white"
        property string tip
        signal clicked()
        width: Kirigami.Units.gridUnit * 1.5; height: width
        radius: width / 2
        color: Qt.rgba(0, 0, 0, cbArea.containsMouse ? 0.7 : 0.5)
        Kirigami.Icon {
            anchors.centerIn: parent
            width: parent.width * 0.68; height: width
            source: cb.iconName
            color: cb.tint
            isMask: true
        }
        MouseArea {
            id: cbArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: cb.clicked()
        }
        QQC2.ToolTip.text: tip
        QQC2.ToolTip.visible: cbArea.containsMouse
        QQC2.ToolTip.delay: 400
    }

    component FolderChip: QQC2.ToolButton {
        id: chip
        property string name
        property string label
        property string iconName
        property bool editable: false
        checkable: true
        checked: page.folder === name
        icon.name: iconName
        text: label + "  " + page.countIn(name)
        onClicked: page.folder = name
        Component.onCompleted: page.chips = page.chips.concat([chip])
        Component.onDestruction: page.chips = page.chips.filter(c => c !== chip)
        Rectangle {     // dossier visé pendant un glisser
            anchors.fill: parent
            radius: Kirigami.Units.cornerRadius
            color: Kirigami.Theme.highlightColor
            opacity: page.dropChip === chip ? 0.35 : 0
        }
        TapHandler {
            acceptedButtons: Qt.RightButton
            enabled: chip.editable
            onTapped: { folderMenu.target = chip.name; folderMenu.popup(); }
        }
    }

    QQC2.Menu {
        id: folderMenu
        property string target
        QQC2.MenuItem {
            icon.name: "edit-rename"; text: page.t("Renommer…", "Rename…")
            onTriggered: { nameDialog.mode = "rename"; nameDialog.old = folderMenu.target; nameDialog.open(); }
        }
        QQC2.MenuItem {
            readonly property var f: page.folderList.find(x => x.name === folderMenu.target) || ({})
            icon.name: "view-hidden"
            text: page.t("Masquer dans « Tous »", "Hide from “All”")
            checkable: true; checked: !!f.hidden
            onTriggered: backend.setFolderHidden(folderMenu.target, checked)
        }
        QQC2.MenuItem { icon.name: "go-previous"; text: page.t("Déplacer à gauche", "Move left"); onTriggered: backend.moveFolder(folderMenu.target, -1) }
        QQC2.MenuItem { icon.name: "go-next"; text: page.t("Déplacer à droite", "Move right"); onTriggered: backend.moveFolder(folderMenu.target, 1) }
        QQC2.MenuSeparator {}
        QQC2.MenuItem {
            icon.name: "edit-delete"; text: page.t("Supprimer le dossier (les fonds restent)", "Delete folder (wallpapers stay)")
            onTriggered: { if (page.folder === folderMenu.target) page.folder = ""; backend.deleteFolder(folderMenu.target); }
        }
    }

    Kirigami.PromptDialog {
        id: nameDialog
        property string mode: "new"      // new | rename | newFor (créer puis y ranger wid)
        property string old: ""
        property string wid: ""
        title: mode === "rename" ? page.t("Renommer le dossier", "Rename folder") : page.t("Nouveau dossier", "New folder")
        standardButtons: Kirigami.Dialog.Ok | Kirigami.Dialog.Cancel
        onOpened: { nameField.text = mode === "rename" ? old : ""; nameField.forceActiveFocus(); }
        onAccepted: {
            const n = nameField.text.trim();
            if (!n) return;
            if (mode === "rename") { if (backend.renameFolder(old, n) && page.folder === old) page.folder = n; }
            else if (backend.createFolder(n) && wid) backend.moveToFolder(wid, n);
        }
        QQC2.TextField {
            id: nameField
            placeholderText: page.t("Nom du dossier", "Folder name")
            onAccepted: nameDialog.accept()
        }
    }

    QQC2.Menu {
        id: filterMenu
        QQC2.Menu {
            title: page.t("Classement d'âge", "Age rating") + (page.ratingFilter ? " : " + page.ratingFilter : "")
            Repeater {
                model: [["", page.t("Tous", "Any")], ["Everyone", page.t("Tout public", "Everyone")],
                        ["Questionable", page.t("Discutable", "Questionable")], ["Mature", page.t("Adulte", "Mature")]]
                delegate: QQC2.MenuItem {
                    required property var modelData
                    text: modelData[1]; checkable: true; checked: page.ratingFilter === modelData[0]
                    onTriggered: page.ratingFilter = modelData[0]
                }
            }
        }
        QQC2.Menu {
            title: page.t("Résolution", "Resolution") + (page.resFilter ? " : " + page.resFilter : "")
            QQC2.MenuItem { text: page.t("Toutes", "Any"); checkable: true; checked: page.resFilter === ""; onTriggered: page.resFilter = "" }
            Repeater {
                model: page.presentRes
                delegate: QQC2.MenuItem {
                    required property var modelData
                    text: modelData; checkable: true; checked: page.resFilter === modelData
                    onTriggered: page.resFilter = modelData
                }
            }
        }
        QQC2.Menu {
            title: page.t("Genre / tag", "Genre / tag") + (page.tagFilter ? " : " + page.tagFilter : "")
            QQC2.MenuItem { text: page.t("Tous", "Any"); checkable: true; checked: page.tagFilter === ""; onTriggered: page.tagFilter = "" }
            Repeater {
                model: page.presentTags
                delegate: QQC2.MenuItem {
                    required property var modelData
                    text: modelData; checkable: true; checked: page.tagFilter === modelData
                    onTriggered: page.tagFilter = modelData
                }
            }
        }
        QQC2.Menu {
            title: page.t("Source", "Source")
            Repeater {
                model: [["", page.t("Toutes", "Any")], ["workshop", "Steam Workshop"], ["mine", page.t("Mes fonds", "My wallpapers")]]
                delegate: QQC2.MenuItem {
                    required property var modelData
                    text: modelData[1]; checkable: true; checked: page.sourceFilter === modelData[0]
                    onTriggered: page.sourceFilter = modelData[0]
                }
            }
        }
        QQC2.MenuSeparator {}
        QQC2.MenuItem { text: page.t("Réagit au son", "Audio responsive"); checkable: true; checked: page.audioOnly; onTriggered: page.audioOnly = checked }
        QQC2.MenuItem { text: page.t("Personnalisable", "Customizable"); checkable: true; checked: page.customOnly; onTriggered: page.customOnly = checked }
        QQC2.MenuItem { text: page.t("Approuvés par Wallpaper Engine", "Approved by Wallpaper Engine"); checkable: true; checked: page.approvedOnly; onTriggered: page.approvedOnly = checked }
        QQC2.MenuSeparator {}
        QQC2.MenuItem {
            icon.name: "edit-clear"; text: page.t("Effacer les filtres", "Clear filters")
            enabled: page.extraFilters > 0
            onTriggered: { page.ratingFilter = ""; page.resFilter = ""; page.tagFilter = ""; page.sourceFilter = "";
                           page.audioOnly = false; page.customOnly = false; page.approvedOnly = false; }
        }
    }

    // menu d'un fond (clic droit)
    QQC2.Menu {
        id: cardMenu
        property var w: ({})
        readonly property bool fav: page.favs.indexOf(w.id) !== -1
        readonly property string inFolder: page.folderOf(w.id || "")
        QQC2.MenuItem { icon.name: "dialog-ok-apply"; text: page.t("Appliquer", "Apply"); onTriggered: backend.setWallpaper(cardMenu.w.id) }
        QQC2.MenuItem {
            icon.name: cardMenu.fav ? "starred-symbolic" : "non-starred-symbolic"
            text: cardMenu.fav ? page.t("Retirer des favoris", "Remove from favorites") : page.t("Ajouter aux favoris", "Add to favorites")
            onTriggered: backend.toggleFavorite(cardMenu.w.id)
        }
        QQC2.MenuItem {
            icon.name: "configure"; text: page.t("Personnaliser…", "Customize…")
            enabled: !!cardMenu.w.customizable
            onTriggered: propsDialog.openFor(cardMenu.w)
        }
        QQC2.Menu {
            title: page.t("Ranger dans", "Move to folder")
            Repeater {
                model: page.folderList
                delegate: QQC2.MenuItem {
                    required property var modelData
                    text: modelData.name; checkable: true; checked: cardMenu.inFolder === modelData.name
                    onTriggered: backend.moveToFolder(cardMenu.w.id, modelData.name)
                }
            }
            QQC2.MenuSeparator { visible: page.folderList.length > 0 }
            QQC2.MenuItem {
                icon.name: "folder-new"; text: page.t("Nouveau dossier…", "New folder…")
                onTriggered: { nameDialog.mode = "newFor"; nameDialog.wid = cardMenu.w.id; nameDialog.open(); }
            }
            QQC2.MenuItem {
                icon.name: "edit-clear"; text: page.t("Sortir du dossier", "Remove from folder")
                enabled: cardMenu.inFolder !== ""
                onTriggered: backend.moveToFolder(cardMenu.w.id, "")
            }
        }
        QQC2.MenuSeparator {}
        QQC2.MenuItem {
            icon.name: "internet-services"; text: page.t("Page du Workshop", "Workshop page")
            enabled: cardMenu.w.source === "workshop"
            onTriggered: backend.openWorkshopPage(cardMenu.w.id)
        }
        QQC2.MenuItem {
            icon.name: "folder-open"; text: page.t("Ouvrir le dossier des fichiers", "Open files folder")
            onTriggered: backend.openFolder(String(cardMenu.w.path).replace(/\/[^/]*$/, ""))
        }
    }

    PropertiesDialog { id: propsDialog }
    Timer {     // captures de développement (WESPAN_SHOT_PROPS=<id>)
        interval: 1200
        running: typeof shotProps !== "undefined" && shotProps !== ""
        onTriggered: {
            const w = backend.wallpapers.find(x => x.id === shotProps);
            if (w) propsDialog.openFor(w);
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
            readonly property bool fav: page.favs.indexOf(modelData.id) !== -1
            readonly property string wid: modelData.id      // lu par les dossiers où l'on dépose

            QQC2.ItemDelegate {
                id: card
                anchors.fill: parent
                anchors.margins: Kirigami.Units.smallSpacing
                highlighted: cell.current
                hoverEnabled: true
                padding: Kirigami.Units.smallSpacing
                QQC2.ToolTip.text: cell.modelData.title + "\n" + page.typeLabel(cell.modelData.type)
                    + (cell.modelData.resolution ? " · " + cell.modelData.resolution : "")
                    + (cell.modelData.size ? " · " + page.fmtSize(cell.modelData.size) : "")
                    + (page.folderOf(cell.modelData.id) ? "\n" + page.t("Dossier : ", "Folder: ") + page.folderOf(cell.modelData.id) : "")
                    + (page.risky.indexOf(cell.modelData.type) !== -1
                       ? "\n" + page.t("⚠ Ce type fonctionne mal sous Proton", "⚠ This type often misbehaves under Proton") : "")
                    + "\n" + page.t("Clic droit : favoris, dossiers, personnaliser…", "Right-click: favorites, folders, customize…")
                QQC2.ToolTip.visible: hovered && !dragArea.drag.active
                QQC2.ToolTip.delay: 900

                contentItem: Item {
                    // clic : appliquer ; glisser : ranger dans un dossier ; clic droit : menu
                    MouseArea {
                        id: dragArea
                        anchors.fill: parent
                        acceptedButtons: Qt.LeftButton | Qt.RightButton
                        drag.target: dragProxy
                        drag.threshold: Kirigami.Units.gridUnit
                        preventStealing: true          // sinon la grille défile au lieu de glisser le fond
                        cursorShape: drag.active ? Qt.ClosedHandCursor : Qt.PointingHandCursor
                        property bool dragged: false     // un glisser n'est pas un clic
                        drag.onActiveChanged: if (drag.active) dragged = true
                        onPressed: (m) => { dragged = false; dragProxy.x = m.x; dragProxy.y = m.y; }
                        onPositionChanged: (m) => {
                            if (!drag.active) return;
                            page.dropChip = page.chipAt(dragArea, m.x, m.y);
                        }
                        onReleased: (m) => {
                            if (drag.active) page.dropOn(page.chipAt(dragArea, m.x, m.y), cell.modelData.id);
                            page.dropChip = null;
                        }
                        onCanceled: page.dropChip = null
                        onClicked: (m) => {
                            if (m.button === Qt.RightButton) { cardMenu.w = cell.modelData; cardMenu.popup(); }
                            else if (!dragged) backend.setWallpaper(cell.modelData.id);
                        }
                    }
                    Item {
                        id: dragProxy
                        width: 1; height: 1
                        // vignette qui suit le pointeur pendant le glisser
                        Rectangle {
                            visible: dragArea.drag.active
                            width: Kirigami.Units.gridUnit * 6; height: width * 9 / 16
                            x: -width / 2; y: -height / 2
                            radius: Kirigami.Units.cornerRadius
                            color: "black"; opacity: 0.85
                            clip: true
                            Image {
                                anchors.fill: parent
                                source: cell.modelData.preview ? "file://" + cell.modelData.preview : ""
                                fillMode: Image.PreserveAspectCrop
                                sourceSize.width: 200
                            }
                        }
                    }

                ColumnLayout {
                    anchors.fill: parent
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
                        // étoile des favoris (visible si favori, ou au survol)
                        CardButton {
                            visible: cell.fav || card.hovered
                            anchors { right: parent.right; bottom: parent.bottom; margins: Kirigami.Units.smallSpacing }
                            iconName: cell.fav ? "starred-symbolic" : "non-starred-symbolic"
                            tint: cell.fav ? "#f5c211" : "white"
                            tip: cell.fav ? page.t("Retirer des favoris", "Remove from favorites") : page.t("Ajouter aux favoris", "Add to favorites")
                            onClicked: backend.toggleFavorite(cell.modelData.id)
                        }
                        CardButton {
                            visible: card.hovered && !!cell.modelData.customizable
                            anchors { left: parent.left; bottom: parent.bottom; margins: Kirigami.Units.smallSpacing }
                            iconName: "configure"
                            tip: page.t("Personnaliser…", "Customize…")
                            onClicked: propsDialog.openFor(cell.modelData)
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
        }

        Kirigami.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 4
            visible: grid.count === 0
            icon.name: page.folder === "__fav" ? "starred-symbolic" : page.folder ? "folder" : "preferences-desktop-wallpaper"
            text: backend.wallpapers.length === 0 ? page.t("Aucun fond d'écran trouvé", "No wallpapers found")
                : page.folder === "__fav" && page.countIn("__fav") === 0 ? page.t("Aucun favori", "No favorites yet")
                : page.folder && page.countIn(page.folder) === 0 ? page.t("Dossier vide", "Empty folder")
                : page.t("Aucun résultat", "No results")
            explanation: backend.wallpapers.length === 0
                ? page.t("Abonnez-vous à des fonds sur le Steam Workshop de Wallpaper Engine.",
                         "Subscribe to wallpapers on the Wallpaper Engine Steam Workshop.")
                : page.folder === "__fav" && page.countIn("__fav") === 0
                ? page.t("Cliquez sur l'étoile d'un fond pour l'ajouter ici.", "Click a wallpaper's star to add it here.")
                : page.folder && page.countIn(page.folder) === 0
                ? page.t("Clic droit sur un fond → « Ranger dans », ou glissez-le sur le dossier.",
                         "Right-click a wallpaper → “Move to folder”, or drag it onto the folder.") : ""
            helpfulAction: Kirigami.Action {
                enabled: backend.wallpapers.length === 0
                text: page.t("Rechercher dans le Workshop", "Search the Workshop"); icon.name: "search"
                onTriggered: applicationWindow().showPage("Search")
            }
        }
    }
}
