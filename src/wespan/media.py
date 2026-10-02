"""Vidéos : version allongée des boucles courtes (voir Daemon.loop_file)."""
import logging
import math
import shutil
import subprocess
from pathlib import Path

from .settings import CACHE_DIR

log = logging.getLogger("wespan.media")

LOOP_DIR = CACHE_DIR / "loops"
LOOP_MIN = 30          # s : en dessous, la vidéo est allongée…
LOOP_TARGET = 60       # s : …jusqu'à environ cette durée
MAX_FILE = 400e6       # octets pour une version allongée
MAX_CACHE = 1.5e9      # octets pour tout le dossier (les plus anciennes partent)


def duration(f: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                             capture_output=True, text=True, timeout=20).stdout
        return float(out.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def extended_loop(f: Path) -> Path | None:
    """Chemin de la version allongée (créée au besoin), ou None si inutile/impossible."""
    f = Path(f)
    try:
        st = f.stat()
    except OSError:
        return None
    out = LOOP_DIR / f"{f.parent.name}-{st.st_size}-{int(st.st_mtime)}{f.suffix or '.mp4'}"
    if out.is_file():
        out.touch()
        return out
    d = duration(f)
    if not d or d >= LOOP_MIN or not shutil.which("ffmpeg"):
        return None
    n = min(math.ceil(LOOP_TARGET / d), int(MAX_FILE // max(st.st_size, 1)))
    if n < 2:
        return None
    LOOP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp" + out.suffix)
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", str(n - 1), "-i", str(f),
                            "-map", "0", "-c", "copy", str(tmp)], capture_output=True, text=True, timeout=120)
        if r.returncode or not tmp.is_file():
            log.warning("could not extend %s: %s", f.name, r.stderr[-300:])
            tmp.unlink(missing_ok=True)
            return None
        tmp.replace(out)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("could not extend %s: %s", f.name, e)
        tmp.unlink(missing_ok=True)
        return None
    log.info("short video (%.1f s): playing a %d× version (%.0f s) for smooth looping", d, n, d * n)
    _trim()
    return out


def _trim():
    files = sorted(LOOP_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = 0
    for p in files:
        total += p.stat().st_size
        if total > MAX_CACHE:
            p.unlink(missing_ok=True)
