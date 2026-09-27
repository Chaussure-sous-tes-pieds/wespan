#!/usr/bin/env bash
# WE Span — uninstall (current user). Your settings (~/.config/wespan) are kept
# unless --purge is given.
set -uo pipefail
SHARE="${XDG_DATA_HOME:-$HOME/.local/share}"

"$HOME/.local/bin/wespan" quit >/dev/null 2>&1
sleep 1
# back to the default Plasma wallpaper on every screen
Q=$(command -v qdbus6 || command -v qdbus-qt6 || command -v qdbus)
"$Q" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript \
    'for (const d of desktops()) if (d.wallpaperPlugin === "org.wespan.wallpaper") d.wallpaperPlugin = "org.kde.image";' >/dev/null
# KWin script, window rule
kwriteconfig6 --file kwinrc --group Plugins --key wespanEnabled false
"$Q" org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript wespan >/dev/null
PYTHONPATH="$SHARE/wespan/lib" python3 -c 'from wespan import desktop; desktop.remove_rule()' 2>/dev/null
kpackagetool6 --type KWin/Script --remove wespan >/dev/null 2>&1
kpackagetool6 --type Plasma/Wallpaper --remove org.wespan.wallpaper >/dev/null 2>&1
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/wespan.desktop" "$HOME/.local/bin/wespan" \
      "$SHARE/applications/wespan.desktop" "$SHARE/icons/hicolor/scalable/apps/wespan.svg"
rm -rf "$SHARE/wespan"
[ "${1:-}" = "--purge" ] && rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/wespan"
echo "WE Span uninstalled. (Wallpaper Engine's Steam launch option is harmless; remove it in"
echo "Steam → Wallpaper Engine → Properties if you like.)"
