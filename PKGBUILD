# Maintainer: Chaussure-sous-tes-pieds <299629219+Chaussure-sous-tes-pieds@users.noreply.github.com>
pkgname=wespan-git
pkgver=1.2.4
pkgrel=1
pkgdesc="Wallpaper Engine (Steam/Proton) as a real KDE Plasma wallpaper on Wayland, spanned across screens"
arch=('any')
url="https://github.com/Chaussure-sous-tes-pieds/wespan"
license=('MIT')
depends=('python' 'python-dbus' 'python-gobject' 'pyside6' 'kirigami' 'kpipewire' 'plasma-workspace'
         'kwin' 'wmctrl' 'xorg-xprop' 'libpulse' 'qt6-tools' 'kconfig' 'kpackage')
optdepends=('steam: Wallpaper Engine is a Steam application'
            'ffmpeg: smooth looping of short video wallpapers')
makedepends=('git')
provides=('wespan')
conflicts=('wespan')
install=wespan.install
source=("wespan::git+${url}.git")
sha256sums=('SKIP')

pkgver() {
    cd wespan
    printf "1.2.4.r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

package() {
    cd wespan
    install -d "$pkgdir/usr/lib/wespan" "$pkgdir/usr/share/wespan"
    cp -r src/wespan "$pkgdir/usr/lib/wespan/"
    find "$pkgdir/usr/lib/wespan" -name __pycache__ -prune -exec rm -rf {} +
    cp -r kwin plasma "$pkgdir/usr/share/wespan/"
    install -d "$pkgdir/usr/share/kwin/scripts" "$pkgdir/usr/share/plasma/wallpapers"
    cp -r kwin/wespan "$pkgdir/usr/share/kwin/scripts/"
    cp -r plasma/org.wespan.wallpaper "$pkgdir/usr/share/plasma/wallpapers/"
    install -Dm755 /dev/stdin "$pkgdir/usr/bin/wespan" <<'SH'
#!/bin/sh
PYTHONPATH="/usr/lib/wespan${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m wespan "$@"
SH
    install -Dm644 data/wespan.desktop "$pkgdir/usr/share/applications/wespan.desktop"
    install -Dm644 data/wespan.svg "$pkgdir/usr/share/icons/hicolor/scalable/apps/wespan.svg"
    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 README.md "$pkgdir/usr/share/doc/wespan/README.md"
}
