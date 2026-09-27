import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Écrans", "Screens")
    function t(fr, en) { return backend.lang === "fr" ? fr : en }
    readonly property var st: backend.state
    readonly property var screens: st.screens || []
    property var offsets: ({})   // copie locale : l'aperçu suit la souris sans attendre le service

    Connections {
        target: backend
        function onStateChanged() { if (!dragging) page.offsets = JSON.parse(JSON.stringify(backend.state.offsets || {})); }
    }
    property bool dragging: false
    Component.onCompleted: offsets = JSON.parse(JSON.stringify(st.offsets || {}))

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
        const cw = st.content ? st.content[0] : (x1 - x0), ch = st.content ? st.content[1] : (y1 - y0);
        const bcx = (x0 + x1) / 2, bcy = (y0 + y1) / 2;
        let z = 1;
        for (const e of s) {
            const o = off(e.name);
            const l = e.x - o.x - bcx, r = l + e.w, tp = e.y - o.y - bcy, b = tp + e.h;
            z = Math.max(z, Math.abs(l) / (cw / 2), Math.abs(r) / (cw / 2), Math.abs(tp) / (ch / 2), Math.abs(b) / (ch / 2));
        }
        return { x0: x0, y0: y0, w: x1 - x0, h: y1 - y0, bcx: bcx, bcy: bcy, z: z, cw: cw, ch: ch };
    }
    readonly property string preview: st.preview ? "file://" + st.preview : ""

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: page.t("Le fond est une seule image étendue sur tous les écrans, selon leur disposition dans "
                       + "Paramètres → Affichage. Si vos écrans ne sont pas à la même hauteur physiquement, décalez "
                       + "l'image de l'un d'eux jusqu'à ce que l'horizon soit aligné. Le zoom s'ajuste tout seul "
                       + "pour ne jamais laisser de bande noire. Les réglages s'appliquent en direct.",
                         "The wallpaper is one image spanned across all screens, following their arrangement in "
                       + "System Settings → Display. If your screens are not at the same physical height, shift one "
                       + "screen's image until the horizon lines up. Zoom adjusts itself so no black bars ever "
                       + "appear. Changes apply live.")
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
                        x: (-page.layout.cw / 2 * page.layout.z + page.layout.bcx + parent.o.x - modelData.x) * diagram.k
                        y: (-page.layout.ch / 2 * page.layout.z + page.layout.bcy + parent.o.y - modelData.y) * diagram.k
                        width: page.layout.cw * page.layout.z * diagram.k
                        height: page.layout.ch * page.layout.z * diagram.k
                        source: page.preview
                        fillMode: Image.PreserveAspectCrop
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
            visible: !!page.layout && page.layout.z > 1.001
            text: page.t("Zoom automatique : ", "Automatic zoom: ") + Math.round(page.layout ? page.layout.z * 100 : 100) + " %"
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
        QQC2.Button {
            icon.name: "preferences-desktop-display"
            text: page.t("Disposition des écrans (Paramètres système)…", "Screen arrangement (System Settings)…")
            onClicked: backend.openDisplaySettings()
        }
    }
}
