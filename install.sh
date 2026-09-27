#!/usr/bin/env bash
# WE Span — installation pour l'utilisateur courant (sans root).
#   ./install.sh            installe / met à jour
#   ./install.sh --steam    et règle l'option de lancement Steam de WE (Steam sera fermé puis relancé)
set -euo pipefail
cd "$(dirname "$0")"

SHARE="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN="$HOME/.local/bin"
DEST="$SHARE/wespan"

need=(python3 steam wmctrl xprop pactl kpackagetool6 kwriteconfig6 kreadconfig6)
missing=()
for c in "${need[@]}"; do command -v "$c" >/dev/null || missing+=("$c"); done
command -v qdbus6 >/dev/null || command -v qdbus-qt6 >/dev/null || command -v qdbus >/dev/null || missing+=(qdbus6)
python3 -c 'import dbus, gi' 2>/dev/null || missing+=("python-dbus/python-gobject")
python3 -c 'import PySide6' 2>/dev/null || missing+=("pyside6")
if ((${#missing[@]})); then
    echo "Manquant / missing : ${missing[*]}"
    echo "Arch / CachyOS : sudo pacman -S --needed python-dbus python-gobject pyside6 kirigami wmctrl xorg-xprop libpulse qt6-tools"
    exit 1
fi

echo "→ fichiers dans $DEST"
rm -rf "$DEST/lib"
mkdir -p "$DEST/lib" "$BIN" "$SHARE/applications" "$SHARE/icons/hicolor/scalable/apps"
cp -r src/wespan "$DEST/lib/"
find "$DEST/lib" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$DEST/kwin" "$DEST/plasma"
cp -r kwin plasma "$DEST/"

cat >"$BIN/wespan" <<EOF
#!/bin/sh
PYTHONPATH="$DEST/lib\${PYTHONPATH:+:\$PYTHONPATH}" exec python3 -m wespan "\$@"
EOF
chmod +x "$BIN/wespan"
cp data/wespan.desktop "$SHARE/applications/"
cp data/wespan.svg "$SHARE/icons/hicolor/scalable/apps/"
command -v update-desktop-database >/dev/null && update-desktop-database "$SHARE/applications" 2>/dev/null || true

case ":$PATH:" in *":$BIN:"*) ;; *) echo "! $BIN n'est pas dans votre PATH" ;; esac

# service déjà lancé : on le redémarre sur la nouvelle version
"$BIN/wespan" quit >/dev/null 2>&1 && sleep 2 || true

echo "→ intégration KDE"
"$BIN/wespan" setup ${1:-}
echo
echo "Terminé. Ouvrez « WE Span » depuis le menu des applications."
