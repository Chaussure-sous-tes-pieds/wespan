import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ScrollablePage {
    id: page
    title: t("Démarrage", "Startup")
    function t(fr, en) { return backend.lang === "fr" ? fr : en }
    readonly property var cfg: backend.cfg

    Kirigami.FormLayout {
        QQC2.Switch {
            Kirigami.FormData.label: page.t("Au démarrage de la session :", "At login:")
            text: page.t("lancer WE Span", "start WE Span")
            checked: backend.autostart
            onToggled: backend.setAutostart(checked)
        }
        QQC2.CheckBox {
            text: page.t("lancer Wallpaper Engine automatiquement (via Steam)", "start Wallpaper Engine automatically (through Steam)")
            checked: page.cfg.start_engine !== false
            enabled: backend.serviceRunning
            onToggled: backend.setSetting("start_engine", checked)
        }
        QQC2.CheckBox {
            text: page.t("le relancer s'il se ferme ou plante", "restart it if it quits or crashes")
            checked: page.cfg.restart_engine !== false
            enabled: backend.serviceRunning
            onToggled: backend.setSetting("restart_engine", checked)
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 30
            wrapMode: Text.Wrap
            opacity: 0.7
            text: page.t("Steam doit pouvoir démarrer : Wallpaper Engine est une application Steam. Tant que le fond "
                       + "n'est pas prêt, Plasma affiche son aperçu fixe.",
                         "Steam must be able to start: Wallpaper Engine is a Steam app. Until the wallpaper is "
                       + "ready, Plasma shows its still preview.")
        }

        QQC2.CheckBox {
            text: page.t("afficher l'icône WE Span dans la zone de notification", "show the WE Span icon in the system tray")
            checked: backend.trayEnabled
            onToggled: backend.setTrayEnabled(checked)
        }
        QQC2.Label {
            Layout.maximumWidth: Kirigami.Units.gridUnit * 30
            wrapMode: Text.Wrap
            opacity: 0.7
            text: page.t("Avec l'icône, fermer cette fenêtre la range dans la zone de notification. Sans elle, "
                       + "la fenêtre se ferme vraiment. Dans les deux cas, le fond d'écran continue de tourner.",
                         "With the icon, closing this window tucks it into the tray. Without it, the window really "
                       + "closes. Either way, the wallpaper keeps running.")
        }

        Kirigami.Separator { Kirigami.FormData.isSection: true }

        QQC2.ComboBox {
            Kirigami.FormData.label: page.t("Langue :", "Language:")
            textRole: "label"; valueRole: "value"
            model: [
                { label: page.t("Automatique", "Automatic"), value: "auto" },
                { label: "Français", value: "fr" },
                { label: "English", value: "en" }
            ]
            currentIndex: Math.max(0, ["auto", "fr", "en"].indexOf(page.cfg.language || "auto"))
            enabled: backend.serviceRunning
            onActivated: backend.setSetting("language", currentValue)
        }
    }
}
