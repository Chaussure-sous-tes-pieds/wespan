# WE Span

**Wallpaper Engine as a real KDE Plasma wallpaper on Wayland — spanned across all your screens, with
cursor, widgets, auto-pause and sound control.**

*[Version française plus bas](#français).*

Wallpaper Engine (Steam, AppID 431960) runs fine under Proton, but its “set as wallpaper” mode relies on a
Windows-only trick (WorkerW) and does nothing on Linux. The usual workaround — a borderless window kept below
the others — hides your cursor, your desktop widgets and the desktop menu. WE Span does it differently:

1. Wallpaper Engine renders into a **hidden, off-screen window** (`-playInWindow`).
2. A **Plasma wallpaper plugin** shows that window's **live video stream** (KWin screencast through PipeWire,
   the same mechanism as task-manager thumbnails). Each screen shows its own part of the picture, so one
   wallpaper spans all monitors seamlessly — portrait screens and different heights included.
3. A tiny **KWin script** keeps the hidden window in place and reports which windows cover each screen.
4. A **service** drives everything: starts Wallpaper Engine through Steam, **pauses it by freezing the process**
   when you work maximized/fullscreen (the last frame stays on screen, 0 % CPU/GPU), restores your volume,
   follows monitors being plugged/unplugged, and restarts Wallpaper Engine if it crashes.
5. A **settings app** (Kirigami) to pick wallpapers, set auto-pause rules, sound, screen alignment, frame rate,
   startup behaviour, plus a diagnostics page with one-click fixes.

Because the result *is* the Plasma wallpaper, everything else keeps working: cursor, widgets, right-click
menu, Show Desktop (Meta+D), multiple virtual desktops and activities.

## Requirements

- KDE Plasma 6 on **Wayland** (tested on Plasma/KWin 6.7, CachyOS)
- Steam with Wallpaper Engine installed and started **once** from Steam (to create its Proton prefix)
- Proton (GE-Proton recommended; tested with GE-Proton 11-7)
- Packages (Arch/CachyOS):
  ```
  sudo pacman -S --needed python-dbus python-gobject pyside6 kirigami wmctrl xorg-xprop libpulse qt6-tools
  ```

## Install

```bash
git clone https://github.com/<you>/wespan.git
cd wespan
./install.sh --steam      # --steam: also adds the required Steam launch option (Steam is closed and reopened)
```

Then open **WE Span** from the application menu. Everything is per-user (no root): files go to
`~/.local/share/wespan`, the command to `~/.local/bin/wespan`. Update by pulling and running `./install.sh`
again; remove with `./uninstall.sh` (`--purge` also deletes your settings).

An AUR-style `PKGBUILD` is included for a system-wide install (run `wespan setup --steam` once per user
afterwards, or open the app → *Diagnostics* → *Fix everything*).

### The Steam launch option

WE Span needs this in *Steam → Wallpaper Engine → Properties → Launch options*:

```
WINE_DISABLE_FULLSCREEN_HACK=1 %command%
```

Without it, Proton's “fullscreen hack” rescales the big hidden window per monitor and the picture gets cut and
misaligned. `install.sh --steam` / the diagnostics page set it for you (Steam must be closed while its config
is edited, so it is closed and restarted automatically).

## Usage

- **Settings app**: `wespan settings` or the *WE Span* launcher.
- **System tray icon** (optional, on by default): click to show/hide the window, menu to pause/mute. With it,
  closing the window just tucks it away; the wallpaper keeps running in any case (it's driven by the service).
- **Right-click the desktop**: mute/unmute, pause/resume, open settings.
- **Command line**: `wespan status | set <id> | mute | unmute | volume 40 | pause | resume | offset HDMI-A-1 0 40 | restart | doctor`

### Auto pause

In *Auto pause*, a screen counts as “covered” when a window is maximized on it, an app is fullscreen on it,
and/or windows cover more than N % of it. Pause when **every** screen is covered (default — as long as some
wallpaper is visible somewhere it keeps playing) or as soon as **one** is. It also pauses while the screen is
locked. Pausing never removes the wallpaper: the last frame stays.

### Screen alignment

Plasma knows where your screens are in pixels, not physically. In *Screens* you can shift each screen's part
of the picture until the horizon lines up; a live preview shows the result and zoom adapts automatically so
no black bars appear.

## Troubleshooting

Open the app → **Diagnostics**: every check has a *Fix* button, and the log can be copied for bug reports
(also in `$XDG_RUNTIME_DIR/wespan/wespan.log`, or run `wespan doctor`).

- **Black screen / only the still preview**: Wallpaper Engine isn't running or hasn't opened the wallpaper yet
  — check *Diagnostics*. The first start through Steam takes ~20 s.
- **“Missing file … wallpaperui.exe” when opening Wallpaper Engine's UI**: the `S:` drive of the Proton prefix
  was removed (this happens if someone runs `proton` by hand without `STEAM_COMPAT_INSTALL_PATH` and
  `STEAM_COMPAT_LIBRARY_PATHS`). *Diagnostics → Wine prefix drive S: → Fix*.
- **Some wallpapers don't work**: *Web* and *Application* wallpapers often fail under Proton; videos (played by
  Plasma) and scenes work well.
- **Sharpness**: the hidden window is exactly as large as all your screens together (Wine doesn't render beyond
  that); pick wallpapers made for your resolution (4K ones look best).

## How it's built (for contributors)

| Part | Where | What it does |
|---|---|---|
| Service | `src/wespan/daemon.py` | DBus `org.wespan.Daemon`; supervises WE, pause logic (SIGSTOP/SIGCONT), audio (`pactl`), writes `$XDG_RUNTIME_DIR/wespan/state.json` |
| Steam/Proton | `src/wespan/steam.py` | libraries, Proton detection, lossless VDF editing (launch option), `S:` drive, WE `config.json` fps |
| KDE glue | `src/wespan/desktop.py` | KWin window rule, KWin script, Plasma wallpaper plugin, autostart |
| KWin script | `kwin/wespan/` | keeps the window off-screen, reports per-screen coverage/maximized/fullscreen |
| Plasma plugin | `plasma/org.wespan.wallpaper/` | `ScreencastingRequest` + `PipeWireSourceItem`, per-screen crop, shared auto-zoom, still-preview fallback |
| Settings app | `src/wespan/gui/` | PySide6 + Kirigami |

Findings worth knowing (they cost a night of debugging):
- KWin shrinks new windows to a single screen → a KWin rule forces the size at creation.
- `_NET_WM_WINDOW_TYPE_DESKTOP` (set with `xprop`) keeps the hidden window out of Show Desktop; the equivalent
  KWin rule is ignored for it.
- Wine won't render beyond the size of the virtual screen: the window is sized to the screens' bounding box.
- When switching wallpapers, Wallpaper Engine may reuse its window and not redraw its bottom rows (stale
  pieces of the previous wallpaper remain): WE Span always opens a fresh window.
- Wallpaper Engine's video player under Proton stutters (software decode, ~10–20 fps for 4K60) and dies when
  videos are switched a few times: WE Span plays *video* wallpapers itself in the Plasma plugin (QtMultimedia,
  GPU decoding, screens kept in sync on a shared clock) and only uses Wallpaper Engine for scenes.
- `closeWallpaper -playInWindow X` closes *every* window; `closeWallpaper -location X` closes only X.
- Two `-control` commands too close together are ignored ("Windows is reentrant") or make WE quit: commands
  are serialized and wait for their effect. Always call WE by its `S:\…` path, like Steam does — a `Z:\…`
  path makes WE think it was moved and rewrite its config on every command.
- `wallpaper64.exe -control pause` does nothing in `-playInWindow` mode; freezing the process does, cleanly.
- Running `proton run` outside Steam without `STEAM_COMPAT_INSTALL_PATH`/`STEAM_COMPAT_LIBRARY_PATHS` deletes the
  prefix's `S:` drive and breaks Wallpaper Engine.

License: MIT. Not affiliated with Wallpaper Engine or Valve.

---

## Français

**Wallpaper Engine comme vrai fond d'écran KDE Plasma sous Wayland — étendu sur tous vos écrans, avec
curseur, widgets, pause automatique et contrôle du son.**

Sous Linux, le mode « définir comme fond d'écran » de Wallpaper Engine ne fonctionne pas (il dépend d'une
astuce propre à Windows). Le contournement habituel — une fenêtre sans bordure maintenue sous les autres —
masque le curseur, les widgets et le menu du bureau. WE Span procède autrement : Wallpaper Engine rend dans une
**fenêtre cachée hors écran**, et un **fond d'écran Plasma** affiche le **flux vidéo en direct** de cette
fenêtre (PipeWire, comme les miniatures de la barre des tâches). Chaque écran en montre sa portion : l'image
est continue d'un écran à l'autre, écrans verticaux et hauteurs différentes compris. C'est un vrai fond Plasma,
donc curseur, widgets, clic droit et Win+D fonctionnent.

Un **service** pilote le tout : il lance Wallpaper Engine via Steam, le **met en pause en le gelant** quand
vous travaillez en plein écran ou fenêtre maximisée (la dernière image reste affichée, 0 % CPU/GPU), réapplique
votre volume, suit le branchement/débranchement des écrans et relance Wallpaper Engine s'il plante. Une
**application de réglages** permet de choisir les fonds, régler la pause, le son, l'alignement des écrans, les
fps et le démarrage, avec une page **Diagnostic** qui répare en un clic.

### Installation

```bash
sudo pacman -S --needed python-dbus python-gobject pyside6 kirigami wmctrl xorg-xprop libpulse qt6-tools
git clone https://github.com/<vous>/wespan.git && cd wespan
./install.sh --steam
```

`--steam` ajoute l'option de lancement indispensable `WINE_DISABLE_FULLSCREEN_HACK=1 %command%` à Wallpaper
Engine (Steam est fermé puis relancé automatiquement, car il réécrit sa configuration en quittant). Lancez
ensuite **WE Span** depuis le menu. Mise à jour : `git pull && ./install.sh`. Désinstallation :
`./uninstall.sh` (`--purge` efface aussi vos réglages).

### Utilisation

- Application : `wespan settings` ou le lanceur *WE Span*.
- Icône dans la zone de notification (optionnelle, activée par défaut) : clic pour afficher/masquer la
  fenêtre, menu pause/son. Le fond continue de tourner même application fermée.
- Clic droit sur le bureau : couper/remettre le son, pause/reprise, réglages.
- Ligne de commande : `wespan status`, `wespan set <id>`, `wespan mute`, `wespan volume 40`, `wespan pause`,
  `wespan offset HDMI-A-1 0 40`, `wespan restart`, `wespan doctor`.

En cas de souci : application → **Diagnostic** (chaque point a son bouton *Réparer*, et le journal peut être
copié pour un rapport de bug).
