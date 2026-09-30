"""Mesure la zone réellement dessinée par WE dans sa fenêtre de rendu, et peut en garder l'image.

Quand Wine n'a pas encore pris la nouvelle disposition des écrans, WE dessine à l'ancienne taille
dans un coin de la fenêtre et laisse le reste noir (ou blanc). Lancé à part
(python -m wespan.probe <xid> [fichier.jpg]) : GDK n'a rien à faire dans le processus du service.
Affiche « largeur hauteur » ; avec un fichier, y enregistre aussi l'image (JPEG).
"""
import os
import sys

STEP = 8        # px entre deux échantillons
MIN_HITS = 5    # échantillons non noirs pour compter une colonne/ligne comme dessinée


def grab(xid: int):
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkX11", "3.0")
    from gi.repository import Gdk, GdkX11
    win = GdkX11.X11Window.foreign_new_for_display(GdkX11.X11Display.get_default(), xid)
    pb = Gdk.pixbuf_get_from_window(win, 0, 0, win.get_width(), win.get_height())
    if pb is None:
        raise RuntimeError("no pixels")
    return pb


def drawn_extent(pb) -> tuple[int, int]:
    w, h = pb.get_width(), pb.get_height()
    px, rs, n = pb.get_pixels(), pb.get_rowstride(), pb.get_n_channels()

    def lit(x, y):
        i = y * rs + x * n
        return px[i] + px[i + 1] + px[i + 2] > 30

    cols = [x for x in range(0, w, STEP) if sum(lit(x, y) for y in range(0, h, STEP)) >= MIN_HITS]
    rows = [y for y in range(0, h, STEP) if sum(lit(x, y) for x in range(0, w, STEP)) >= MIN_HITS]
    return (cols[-1] + STEP if cols else 0), (rows[-1] + STEP if rows else 0)


if __name__ == "__main__":
    os.environ["GDK_BACKEND"] = "x11"
    try:
        pb = grab(int(sys.argv[1], 16))
        print(*drawn_extent(pb))
        if len(sys.argv) > 2:
            pb.savev(sys.argv[2], "jpeg", ["quality"], ["90"])
    except Exception as e:  # noqa: BLE001 - le service ne veut qu'un oui/non
        print(e, file=sys.stderr)
        sys.exit(1)
