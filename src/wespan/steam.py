"""Tout ce qui touche à Steam : bibliothèques, Proton, options de lancement, préfixe, Workshop."""
import glob
import json
import os
import re
from pathlib import Path

from .settings import WE_APPID

LAUNCH_OPTION = "WINE_DISABLE_FULLSCREEN_HACK=1 %command%"
FSHACK_VAR = "WINE_DISABLE_FULLSCREEN_HACK=1"


# --- VDF texte (sans perte : les chaînes sont gardées brutes, échappements compris) ----------

def vdf_parse(text: str) -> list:
    """Retourne une liste de [clé, valeur] ; une valeur est une chaîne ou une liste imbriquée."""
    tokens = re.findall(r'"((?:[^"\\]|\\.)*)"|([{}])', text)
    pos = 0

    def parse_obj():
        nonlocal pos
        out = []
        while pos < len(tokens):
            s, brace = tokens[pos]
            if brace == "}":
                pos += 1
                return out
            key = s
            pos += 1
            s2, brace2 = tokens[pos]
            if brace2 == "{":
                pos += 1
                out.append([key, parse_obj()])
            else:
                pos += 1
                out.append([key, s2])
        return out

    return parse_obj()


def vdf_dump(obj: list, depth: int = 0) -> str:
    ind = "\t" * depth
    out = []
    for key, val in obj:
        if isinstance(val, list):
            out.append(f'{ind}"{key}"\n{ind}{{\n{vdf_dump(val, depth + 1)}{ind}}}\n')
        else:
            out.append(f'{ind}"{key}"\t\t"{val}"\n')
    return "".join(out)


def vdf_get(obj, *path):
    for p in path:
        if not isinstance(obj, list):
            return None
        obj = next((v for k, v in obj if k.lower() == p.lower()), None)
    return obj


def vdf_child(obj: list, key: str) -> list:
    """Sous-objet 'key' (créé s'il manque)."""
    for item in obj:
        if item[0].lower() == key.lower() and isinstance(item[1], list):
            return item[1]
    new = []
    obj.append([key, new])
    return new


# --- emplacements ------------------------------------------------------------------------------

def steam_root() -> Path | None:
    for c in ("~/.local/share/Steam", "~/.steam/steam", "~/.steam/root",
              "~/.var/app/com.valvesoftware.Steam/.local/share/Steam"):
        p = Path(c).expanduser()
        if (p / "steamapps").is_dir():
            return p.resolve()
    return None


def libraries(root: Path) -> list[Path]:
    libs = [root]
    try:
        data = vdf_parse((root / "steamapps/libraryfolders.vdf").read_text(errors="replace"))
        for _, entry in vdf_get(data, "libraryfolders") or []:
            if isinstance(entry, list) and (p := vdf_get(entry, "path")):
                libs.append(Path(p.replace("\\\\", "\\")))
    except OSError:
        pass
    seen, out = set(), []
    for lib in libs:
        r = lib.resolve() if lib.exists() else lib
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


class SteamInfo:
    """Chemins utiles pour Wallpaper Engine sur cette machine."""

    def __init__(self, proton_override: str = ""):
        self.root = steam_root()
        self.library = None
        self.we_dir = None
        if self.root:
            for lib in libraries(self.root):
                if (lib / "steamapps/common/wallpaper_engine/wallpaper64.exe").exists():
                    self.library, self.we_dir = lib, lib / "steamapps/common/wallpaper_engine"
                    break
        lib = self.library or self.root
        self.compatdata = lib / "steamapps/compatdata" / WE_APPID if lib else None
        self.workshop = lib / "steamapps/workshop/content" / WE_APPID if lib else None
        self.proton = Path(proton_override) if proton_override else find_proton(self)

    @property
    def ok(self) -> bool:
        return bool(self.root and self.we_dir and self.proton and self.proton.exists())

    def env(self) -> dict:
        env = dict(os.environ)
        env.update({
            "STEAM_COMPAT_CLIENT_INSTALL_PATH": str(self.root),
            "STEAM_COMPAT_DATA_PATH": str(self.compatdata),
            # indispensables : sans elles, proton supprime le lecteur S: dont WE a besoin
            "STEAM_COMPAT_INSTALL_PATH": str(self.we_dir),
            "STEAM_COMPAT_LIBRARY_PATHS": str(self.library / "steamapps"),
        })
        return env


def _proc_cmdlines():
    for d in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            yield Path(d).read_bytes().split(b"\0")
        except OSError:
            continue


def find_proton(info: "SteamInfo") -> Path | None:
    # 1. celui qui fait tourner WE en ce moment (le plus fiable)
    for args in _proc_cmdlines():
        a = [x.decode(errors="replace") for x in args]
        if any("wallpaper_engine" in x for x in a):
            for x in a:
                if x.endswith("/proton") and Path(x).exists():
                    return Path(x)
    if not info.root:
        return None
    # 2. l'outil de compatibilité choisi dans Steam pour WE
    name = ""
    try:
        cfg = vdf_parse((info.root / "config/config.vdf").read_text(errors="replace"))
        m = vdf_get(cfg, "InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping", WE_APPID)
        name = vdf_get(m, "name") or ""
    except OSError:
        pass
    tools = {}
    for d in [info.root / "compatibilitytools.d", Path("/usr/share/steam/compatibilitytools.d")]:
        for vdf in glob.glob(str(d / "*/compatibilitytool.vdf")):
            try:
                txt = Path(vdf).read_text(errors="replace")
                for internal in re.findall(r'"compat_tools"\s*\{\s*"([^"]+)"', txt):
                    tools[internal] = Path(vdf).parent / "proton"
            except OSError:
                pass
    for lib in libraries(info.root):
        for p in glob.glob(str(lib / "steamapps/common/Proton*/proton")):
            d = Path(p).parent.name              # "Proton - Experimental", "Proton 9.0"...
            key = "proton_experimental" if "Experimental" in d else "proton_" + re.sub(r"\D", "", d.split(".")[0])
            tools.setdefault(key, Path(p))
            tools.setdefault(d, Path(p))
    if name and name in tools and tools[name].exists():
        return tools[name]
    # 3. à défaut : un GE-Proton, sinon Proton Experimental
    ge = sorted((p for k, p in tools.items() if "GE-Proton" in k and p.exists()), key=lambda p: p.parent.name)
    if ge:
        return ge[-1]
    return tools.get("proton_experimental")


# --- options de lancement (Steam doit être fermé pour les modifier) ------------------------

def _localconfigs(info: SteamInfo) -> list[Path]:
    return [Path(p) for p in glob.glob(str(info.root / "userdata/*/config/localconfig.vdf"))] if info.root else []


def launch_options(info: SteamInfo) -> list[str]:
    out = []
    for f in _localconfigs(info):
        try:
            data = vdf_parse(f.read_text(errors="replace"))
            apps = vdf_get(data, "UserLocalConfigStore", "Software", "Valve", "Steam", "apps")
            out.append(vdf_get(apps, WE_APPID, "LaunchOptions") or "")
        except OSError:
            pass
    return out


def launch_option_ok(info: SteamInfo) -> bool:
    opts = launch_options(info)
    return bool(opts) and all(FSHACK_VAR in o for o in opts)


def set_launch_option(info: SteamInfo) -> int:
    """Ajoute la variable aux options de lancement de WE. Retourne le nombre de fichiers modifiés."""
    n = 0
    for f in _localconfigs(info):
        text = f.read_text(errors="replace")
        data = vdf_parse(text)
        store = vdf_child(data, "UserLocalConfigStore")
        apps = vdf_child(vdf_child(vdf_child(vdf_child(store, "Software"), "Valve"), "Steam"), "apps")
        app = vdf_child(apps, WE_APPID)
        cur = vdf_get(app, "LaunchOptions")
        if cur is not None and FSHACK_VAR in cur:
            continue
        if cur is None:
            app.insert(0, ["LaunchOptions", LAUNCH_OPTION])
        else:
            new = cur if "%command%" in cur else (cur + " %command%").strip()
            for item in app:
                if item[0] == "LaunchOptions":
                    item[1] = f"{FSHACK_VAR} {new}"
        backup = f.with_suffix(".vdf.wespan-backup")
        if not backup.exists():
            backup.write_text(text)
        f.write_text(vdf_dump(data))
        n += 1
    return n


def steam_running() -> bool:
    for c in glob.glob("/proc/[0-9]*/comm"):
        try:
            if Path(c).read_text().strip() == "steam":
                return True
        except OSError:
            pass
    return False


# --- préfixe Wine ---------------------------------------------------------------------------

def drive_s_ok(info: SteamInfo) -> bool:
    if not info.compatdata:
        return False
    s = info.compatdata / "pfx/dosdevices/s:"
    return s.is_symlink() and Path(os.readlink(s)).resolve() == info.library.resolve()


def fix_drive_s(info: SteamInfo) -> None:
    s = info.compatdata / "pfx/dosdevices/s:"
    if s.is_symlink() or s.exists():
        s.unlink()
    s.symlink_to(info.library)


# --- réglages de Wallpaper Engine -----------------------------------------------------------

def we_fps(info: SteamInfo) -> int | None:
    try:
        m = re.search(r'"fps"\s*:\s*(\d+)', (info.we_dir / "config.json").read_text(errors="replace"))
        return int(m.group(1)) if m else None
    except OSError:
        return None


def set_we_fps(info: SteamInfo, fps: int) -> bool:
    """À faire WE arrêté (il réécrit son fichier en quittant)."""
    f = info.we_dir / "config.json"
    text = f.read_text(errors="replace")
    new, n = re.subn(r'("fps"\s*:\s*)\d+', lambda m: m.group(1) + str(int(fps)), text)
    if n:
        f.write_text(new)
    return bool(n)


# --- Workshop -------------------------------------------------------------------------------

def list_wallpapers(info: SteamInfo) -> list[dict]:
    out = []
    dirs = []
    if info.workshop and info.workshop.is_dir():
        dirs += sorted(info.workshop.iterdir())
    if info.we_dir and (info.we_dir / "projects/myprojects").is_dir():
        dirs += sorted((info.we_dir / "projects/myprojects").iterdir())
    for d in dirs:
        pj = d / "project.json"
        try:
            p = json.loads(pj.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        prev = p.get("preview") or ""
        prev = str(d / prev) if prev and (d / prev).exists() else ""
        out.append({
            "id": d.name,
            "path": str(pj),
            "title": str(p.get("title") or d.name).strip(),
            "type": str(p.get("type") or "").lower(),
            "preview": prev,
            "tags": p.get("tags") or [],
            "mtime": int(pj.stat().st_mtime),
        })
    return out


def wallpaper_path(info: SteamInfo, wid: str) -> Path | None:
    for base in (info.workshop, info.we_dir / "projects/myprojects" if info.we_dir else None):
        if base and (base / wid / "project.json").exists():
            return base / wid / "project.json"
    return None
