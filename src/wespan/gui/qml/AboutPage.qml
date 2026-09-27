import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("À propos", "About")
    function t(fr, en) { return backend.lang === "fr" ? fr : backend.lang === "en" ? en : backend.translate(en) }

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing
        RowLayout {
            spacing: Kirigami.Units.largeSpacing
            Kirigami.Icon { source: "wespan"; fallback: "preferences-desktop-wallpaper"; implicitWidth: Kirigami.Units.iconSizes.enormous; implicitHeight: implicitWidth }
            ColumnLayout {
                Kirigami.Heading { text: "WE Span " + backend.version }
                QQC2.Label { text: page.t("Wallpaper Engine comme vrai fond d'écran KDE Plasma (Wayland)", "Wallpaper Engine as a real KDE Plasma wallpaper (Wayland)") }
            }
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            textFormat: Text.StyledText
            text: page.t(
                "<b>Comment ça marche</b><br>"
              + "Wallpaper Engine (Steam, via Proton) rend le fond dans une fenêtre cachée hors écran. Le fond "
              + "d'écran Plasma « WE Span » affiche le flux vidéo de cette fenêtre (PipeWire, comme les miniatures "
              + "de la barre des tâches) et chaque écran en montre la portion qui lui correspond. C'est donc un vrai "
              + "fond Plasma : curseur, widgets et menu du bureau fonctionnent, et l'image est continue d'un écran à "
              + "l'autre.<br><br>"
              + "Un petit script KWin garde la fenêtre cachée et indique quelles fenêtres recouvrent vos écrans ; le "
              + "service met alors Wallpaper Engine en pause en le gelant (l'image reste, figée, sans consommer de "
              + "ressources).<br><br>"
              + "<b>Limites connues</b><br>"
              + "• Wallpaper Engine est une application Steam : Steam doit tourner.<br>"
              + "• Le bouton « Appliquer » de l'interface de Wallpaper Engine ne fonctionne pas sous Linux : "
              + "choisissez les fonds ici.<br>"
              + "• Les fonds de type Web/Application fonctionnent mal sous Proton.<br>"
              + "• Wayland + KDE Plasma 6 requis.",
                "<b>How it works</b><br>"
              + "Wallpaper Engine (Steam, through Proton) renders into a hidden off-screen window. The “WE Span” "
              + "Plasma wallpaper shows that window's live video stream (PipeWire, like task manager thumbnails) and "
              + "each screen displays its own part of it. So it is a real Plasma wallpaper: cursor, widgets and the "
              + "desktop menu work, and the picture is continuous across screens.<br><br>"
              + "A small KWin script keeps the window hidden and reports which windows cover your screens; the service "
              + "then pauses Wallpaper Engine by freezing it (the picture stays, frozen, using no resources).<br><br>"
              + "<b>Known limitations</b><br>"
              + "• Wallpaper Engine is a Steam app: Steam has to be running.<br>"
              + "• The “Apply” button in Wallpaper Engine's own UI does not work on Linux: pick wallpapers here.<br>"
              + "• Web/Application wallpapers often misbehave under Proton.<br>"
              + "• Requires Wayland + KDE Plasma 6.")
        }
        QQC2.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            text: page.t("WE Span n'est pas affilié à Wallpaper Engine ni à Valve. Licence MIT.",
                         "WE Span is not affiliated with Wallpaper Engine or Valve. MIT license.")
        }
    }
}
