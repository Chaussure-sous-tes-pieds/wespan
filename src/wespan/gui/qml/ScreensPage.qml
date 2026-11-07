import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Écrans", "Screens")
    function t(fr, en) { return backend.lang === "fr" ? fr : backend.lang === "en" ? en : backend.translate(en) }
    readonly property var st: backend.state
    readonly property var screens: st.screens || []
    property var offsets: ({})   // copie locale : l'aperçu suit la souris sans attendre le service

    Connections {
        target: backend
        function onStateChanged() {
            if (!dragging) page.offsets = JSON.parse(JSON.stringify(backend.state.offsets || {}));
            if (!page.viewEditing) page.view = page.cleanView(backend.state.wallpaperView || backend.state.view);
        }
    }
    property bool dragging: false
    Component.onCompleted: { offsets = JSON.parse(JSON.stringify(st.offsets || {})); view = cleanView(st.wallpaperView || st.view); }

    // --- cadrage du fond affiché (copie locale, envoyée au service un instant après le dernier geste)
    property var view: cleanView(null)
    readonly property bool viewEditing: sendView.running || zoomSlider.pressed || xSlider.pressed || ySlider.pressed
    function cleanView(v) {
        v = v || {};
        return { fit: v.fit || "fill", zoom: v.zoom || 100, x: v.x || 0, y: v.y || 0 };
    }
    function editView(key, value) {
        const v = Object.assign({}, view);
        v[key] = value;
        view = v;
        sendView.restart();
    }
    // (comme framing.needs_native : tout cadrage réglé => WE rend le fond entier, à ses proportions)
    function needsNative(v) { return !!v && (v.fit !== "fill" || v.zoom !== 100 || v.x !== 0 || v.y !== 0); }
    Timer {
        id: sendView
        interval: 500
        onTriggered: backend.setView(page.st.wallpaper || "", page.view)
    }

    function off(name) { const o = offsets[name]; return o ? o : { x: 0, y: 0 }; }
    function setOff(name, x, y) {
        const o = Object.assign({}, offsets);
        o[name] = { x: x, y: y };
        offsets = o;
        backend.setOffset(name, x, y);
    }

    // même calcul que le fond d'écran Plasma (zoom commun, centré sur le rectangle englobant)
    readonly property var layout: {
        const s = screens;
        if (!s.length) return null;
        let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
        for (const e of s) { x0 = Math.min(x0, e.x); y0 = Math.min(y0, e.y); x1 = Math.max(x1, e.x + e.w); y1 = Math.max(y1, e.y + e.h); }
        const bw = x1 - x0, bh = y1 - y0;
        // zone rendue : celle qu'aura WE avec ce cadrage (proportions du fond s'il faut le fond entier)
        let cw = st.content ? st.content[0] : bw, ch = st.content ? st.content[1] : bh;
        const v = view;
        if (needsNative(v) && st.native) {
            const k = Math.min(bw / st.native[0], bh / st.native[1]);
            cw = Math.floor(st.native[0] * k / 2) * 2; ch = Math.floor(st.native[1] * k / 2) * 2;
        } else if (needsNative(st.wallpaperView || st.view)) {
            cw = bw; ch = bh;
        }
        const bcx = (x0 + x1) / 2, bcy = (y0 + y1) / 2;
        let ax = 0, ay = 0;
        for (const e of s) {
            const o = off(e.name);
            const l = e.x - o.x - bcx, r = l + e.w, tp = e.y - o.y - bcy, b = tp + e.h;
            ax = Math.max(ax, Math.abs(l) / (cw / 2), Math.abs(r) / (cw / 2));
            ay = Math.max(ay, Math.abs(tp) / (ch / 2), Math.abs(b) / (ch / 2));
        }
        // même calcul que le fond Plasma (main.qml, computeLayout)
        let zx, zy;
        if (v.fit === "fit") { zx = zy = Math.min(bw / cw, bh / ch); }
        else if (v.fit === "stretch") { zx = ax; zy = ay; }
        else { zx = zy = Math.max(1, ax, ay); }
        const auto = Math.max(zx, zy);
        zx *= v.zoom / 100; zy *= v.zoom / 100;
        const panX = v.x / 100 * Math.abs(cw * zx - bw) / 2, panY = v.y / 100 * Math.abs(ch * zy - bh) / 2;
        return { x0: x0, y0: y0, w: bw, h: bh, bcx: bcx + panX, bcy: bcy + panY, zx: zx, zy: zy, auto: auto, cw: cw, ch: ch };
    }
    readonly property string preview: st.preview ? "file://" + st.preview : ""

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: page.t("Le fond est une seule image étendue sur tous les écrans, selon leur disposition dans "
                       + "Paramètres → Affichage. Si vos écrans ne sont pas à la même hauteur physiquement, décalez "
                       + "l'image de l'un d'eux jusqu'à ce que l'horizon soit aligné. En mode « Remplir » (par défaut), "
                       + "le zoom s'ajuste tout seul pour ne jamais laisser de bande noire. Les réglages s'appliquent en direct.",
                         "The wallpaper is one image spanned across all screens, following their arrangement in "
                       + "System Settings → Display. If your screens are not at the same physical height, shift one "
                       + "screen's image until the horizon lines up. In \"Fill\" mode (the default), zoom adjusts itself "
                       + "so no black bars ever appear. Changes apply live.")
        }

        // --- aperçu ----------------------------------------------------------------------------
        Item {
            id: diagram
            Layout.fillWidth: true
            Layout.preferredHeight: page.layout ? Math.min(Kirigami.Units.gridUnit * 18, width * page.layout.h / page.layout.w) : 0
            visible: !!page.layout
            readonly property real k: page.layout ? Math.min(width / page.layout.w, height / page.layout.h) : 1
            readonly property real ox: page.layout ? (width - page.layout.w * k) / 2 : 0

            Repeater {
                model: page.screens
                delegate: Rectangle {
                    required property var modelData
                    readonly property var o: page.off(modelData.name)
                    x: diagram.ox + (modelData.x - page.layout.x0) * diagram.k
                    y: (modelData.y - page.layout.y0) * diagram.k
                    width: modelData.w * diagram.k
                    height: modelData.h * diagram.k
                    color: "black"
                    border.color: Kirigami.Theme.highlightColor
                    border.width: 2
                    clip: true
                    Image {
                        // coin haut-gauche de la zone rendue, vu depuis cet écran (cf. plugin)
                        x: (-page.layout.cw / 2 * page.layout.zx + page.layout.bcx + parent.o.x - modelData.x) * diagram.k
                        y: (-page.layout.ch / 2 * page.layout.zy + page.layout.bcy + parent.o.y - modelData.y) * diagram.k
                        width: page.layout.cw * page.layout.zx * diagram.k
                        height: page.layout.ch * page.layout.zy * diagram.k
                        source: page.preview
                        fillMode: page.view.fit === "stretch" ? Image.Stretch : Image.PreserveAspectCrop
                        asynchronous: true
                        sourceSize.width: 1024
                    }
                    Rectangle {
                        anchors { left: parent.left; bottom: parent.bottom; margins: 4 }
                        color: Qt.rgba(0, 0, 0, 0.6); radius: 3
                        implicitWidth: nm.implicitWidth + 8; implicitHeight: nm.implicitHeight + 4
                        QQC2.Label { id: nm; anchors.centerIn: parent; color: "white"; text: modelData.name }
                    }
                }
            }
        }
        QQC2.Label {
            visible: !!page.layout && page.view.fit === "fill" && page.layout.auto > 1.001
            text: page.t("Zoom automatique : ", "Automatic zoom: ") + Math.round(page.layout ? page.layout.auto * 100 : 100) + " %"
            opacity: 0.7
        }

        // --- réglages par écran ------------------------------------------------------------------
        Kirigami.FormLayout {
            Layout.fillWidth: true
            Repeater {
                model: page.screens
                delegate: RowLayout {
                    required property var modelData
                    readonly property var o: page.off(modelData.name)
                    Kirigami.FormData.label: modelData.name + " (" + modelData.w + "×" + modelData.h + ") :"
                    QQC2.Label { text: page.t("vertical", "vertical") }
                    QQC2.SpinBox {
                        from: -2000; to: 2000; stepSize: 5; editable: true
                        value: o.y
                        onValueModified: page.setOff(modelData.name, o.x, value)
                    }
                    QQC2.Label { text: page.t("horizontal", "horizontal") }
                    QQC2.SpinBox {
                        from: -2000; to: 2000; stepSize: 5; editable: true
                        value: o.x
                        onValueModified: page.setOff(modelData.name, value, o.y)
                    }
                    QQC2.ToolButton {
                        icon.name: "edit-undo"
                        enabled: o.x !== 0 || o.y !== 0
                        onClicked: page.setOff(modelData.name, 0, 0)
                        QQC2.ToolTip.text: page.t("Remettre à zéro", "Reset"); QQC2.ToolTip.visible: hovered
                    }
                }
            }
        }
        QQC2.Label {
            opacity: 0.7
            text: page.t("Valeur positive : l'image de cet écran descend / va vers la droite.",
                         "Positive values move that screen's image down / to the right.")
        }
        // --- cadrage du fond affiché ---------------------------------------------------------------
        Kirigami.Separator { Layout.fillWidth: true; Layout.topMargin: Kirigami.Units.largeSpacing }
        Kirigami.Heading { level: 3; text: page.t("Cadrage de ce fond", "Framing of this wallpaper") }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.8
            text: page.t("Si le fond est mal cadré (bords coupés, image trop grande ou décalée), choisissez comment "
                       + "il remplit vos écrans, zoomez et déplacez-le. L'aperçu ci-dessus suit vos réglages.",
                         "If the wallpaper does not fit well (edges cut off, too big, off-centre), choose how it fills "
                       + "your screens, zoom and move it. The preview above follows your changes.")
        }
        Kirigami.FormLayout {
            Layout.fillWidth: true
            QQC2.ComboBox {
                id: fitBox
                Kirigami.FormData.label: page.t("Ajustement :", "Fit:")
                readonly property var fits: ["fill", "fit", "stretch"]
                model: [page.t("Remplir les écrans (rogne les bords)", "Fill the screens (crops the edges)"),
                        page.t("Ajuster (fond entier, bandes noires)", "Fit (whole wallpaper, black bars)"),
                        page.t("Étirer (déforme l'image)", "Stretch (distorts the picture)")]
                currentIndex: Math.max(0, fits.indexOf(page.view.fit))
                onActivated: index => page.editView("fit", fits[index])
            }
            RowLayout {
                Kirigami.FormData.label: page.t("Zoom :", "Zoom:")
                QQC2.Slider {
                    id: zoomSlider
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                    from: 25; to: 400; stepSize: 5
                    value: page.view.zoom
                    onMoved: page.editView("zoom", Math.round(value))
                }
                QQC2.SpinBox {
                    from: 25; to: 400; stepSize: 5; editable: true
                    value: page.view.zoom
                    textFromValue: (v, l) => v + " %"
                    valueFromText: (txt, l) => parseInt(txt) || 100
                    onValueModified: page.editView("zoom", value)
                }
            }
            RowLayout {
                Kirigami.FormData.label: page.t("Position horizontale :", "Horizontal position:")
                QQC2.Slider {
                    id: xSlider
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                    from: -100; to: 100; stepSize: 1
                    value: page.view.x
                    onMoved: page.editView("x", Math.round(value))
                }
                QQC2.Label { text: page.view.x; Layout.minimumWidth: Kirigami.Units.gridUnit * 2 }
            }
            RowLayout {
                Kirigami.FormData.label: page.t("Position verticale :", "Vertical position:")
                QQC2.Slider {
                    id: ySlider
                    Layout.preferredWidth: Kirigami.Units.gridUnit * 14
                    from: -100; to: 100; stepSize: 1
                    value: page.view.y
                    onMoved: page.editView("y", Math.round(value))
                }
                QQC2.Label { text: page.view.y; Layout.minimumWidth: Kirigami.Units.gridUnit * 2 }
            }
            RowLayout {
                QQC2.Button {
                    icon.name: "edit-undo"
                    text: page.t("Réinitialiser", "Reset")
                    enabled: !!page.st.ownView
                    onClicked: { sendView.stop(); backend.setView(page.st.wallpaper || "", null); page.view = page.cleanView(page.st.wallpaperView || page.st.view); }
                }
                QQC2.Button {
                    icon.name: "edit-copy"
                    text: page.t("Utiliser pour tous les fonds", "Use for all wallpapers")
                    onClicked: {
                        sendView.stop();
                        backend.setDefaultView(page.view);
                        backend.setView(page.st.wallpaper || "", null);
                    }
                    QQC2.ToolTip.text: page.t("Devient le cadrage de tous les fonds qui n'ont pas le leur.",
                                              "Becomes the framing of every wallpaper that has none of its own.")
                    QQC2.ToolTip.visible: hovered
                }
            }
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            text: (page.st.ownView ? page.t("Réglage propre à ce fond.", "This wallpaper's own setting.")
                                   : page.t("Cadrage par défaut (commun à tous les fonds sans réglage propre).",
                                            "Default framing (shared by every wallpaper without its own)."))
                + (page.needsNative(page.view) && !page.st.native
                   ? " " + page.t("Ce fond ne peut pas être montré en entier (taille d'origine inconnue) : seuls le zoom et la position s'appliquent.",
                                  "This wallpaper cannot be shown whole (original size unknown): only zoom and position apply.")
                   : page.needsNative(page.view) && page.st.mode !== "video"
                   ? " " + page.t("Wallpaper Engine rend alors la scène entière, à ses proportions d'origine (quelques secondes au premier réglage, puis tout est instantané).",
                                  "Wallpaper Engine then renders the whole scene at its original proportions (a few seconds for the first change, then everything is instant).")
                   : "")
        }
        QQC2.Button {
            icon.name: "preferences-desktop-display"
            text: page.t("Disposition des écrans (Paramètres système)…", "Screen arrangement (System Settings)…")
            onClicked: backend.openDisplaySettings()
        }
    }
}
