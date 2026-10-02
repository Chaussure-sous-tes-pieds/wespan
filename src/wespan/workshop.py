"""Recherche dans le Steam Workshop de Wallpaper Engine.

Sans clé : la page publique de recherche du Workshop donne les identifiants, et
ISteamRemoteStorage/GetPublishedFileDetails (sans clé) leurs détails. Avec une clé Steam Web API
(facultative), IPublishedFileService/QueryFiles fait tout d'un coup, plus proprement.
S'abonner n'est possible que depuis le client Steam : on y ouvre la page du fond, Steam le
télécharge, et il apparaît dans la liste des fonds.
"""
import json
import re
import urllib.parse
import urllib.request

from .settings import WE_APPID

PER_PAGE = 30
UA = "Mozilla/5.0 (X11; Linux x86_64) WE-Span"
TYPES = ("Scene", "Video", "Web", "Application")
RATINGS = ("Everyone", "Questionable", "Mature")
NOISE_TAGS = ("Wallpaper", "Approved")
# tags de résolution du Workshop (« 3840 x 2160 », « Dual Monitor »…)
RES_TAG = re.compile(r"^(\d+ x \d+|Dual Monitor|Triple Monitor|Ultrawide.*|Portrait.*|Other resolution)$", re.I)
GENRES = ("Abstract", "Animal", "Anime", "Cartoon", "CGI", "Cyberpunk", "Fantasy", "Game", "Girls", "Guys",
          "Landscape", "Medieval", "Memes", "MMD", "Music", "Nature", "Pixel art", "Relaxing", "Retro", "Sci-Fi",
          "Sports", "Technology", "Television", "Vehicle", "Unspecified")
RESOLUTIONS = ("1280 x 720", "1920 x 1080", "2560 x 1440", "3840 x 2160", "Ultrawide Standard",
               "Ultrawide Quad HD", "Dual Monitor", "Triple Monitor", "Portrait Full HD", "Other resolution")
# tri de l'appli -> (page web, QueryFiles query_type)
SORTS = {
    "trend": ("trend", 3),
    "popular": ("totaluniquesubscribers", 9),
    "recent": ("mostrecent", 1),
    "relevance": ("textsearch", 12),
}


class WorkshopError(Exception):
    pass


def _get(url: str, data: dict | None = None, timeout: float = 20) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except OSError as e:
        raise WorkshopError(str(e)) from e


def search(text: str = "", sort: str = "trend", page: int = 1, kind: str = "", rating: str = "Everyone",
           key: str = "") -> dict:
    """{"items": [...], "total": n, "page": p, "pages": n}. kind : "" ou un de TYPES ; rating : un de
    RATINGS ou "" (tous)."""
    sort = sort if sort in SORTS else "trend"
    if text and sort == "trend":
        sort = "relevance"
    tags = [t for t in (kind, rating) if t]
    if key:
        return _search_api(text, sort, page, tags, key)
    return _search_web(text, sort, page, tags)


def _search_web(text, sort, page, tags):
    q = [("appid", WE_APPID), ("section", "readytouseitems"), ("browsesort", SORTS[sort][0]),
         ("actualsort", SORTS[sort][0]), ("p", str(page)), ("numperpage", str(PER_PAGE))]
    if sort == "trend":
        q.append(("days", "7"))
    if text:
        q.append(("searchtext", text))
    q += [("requiredtags[]", t) for t in tags]
    html = _get("https://steamcommunity.com/workshop/browse/?" + urllib.parse.urlencode(q)).decode("utf-8", "replace")
    ids = list(dict.fromkeys(re.findall(r"sharedfiles/filedetails/\?id=(\d+)", html)))
    m = re.search(r"([\d,.\s ]+)\s+entries", html)
    total = int(re.sub(r"\D", "", m[1])) if m else len(ids)
    items = details(ids)
    return {"items": items, "total": total, "page": page, "pages": max(1, -(-total // PER_PAGE))}


def _search_api(text, sort, page, tags, key):
    q = [("key", key), ("appid", WE_APPID), ("query_type", str(SORTS[sort][1])), ("page", str(page)),
         ("numperpage", str(PER_PAGE)), ("return_tags", "true"), ("return_previews", "true"),
         ("return_vote_data", "true"), ("match_all_tags", "true")]
    if sort == "trend":
        q.append(("days", "7"))
    if text:
        q.append(("search_text", text))
    q += [(f"requiredtags[{i}]", t) for i, t in enumerate(tags)]
    raw = _get("https://api.steampowered.com/IPublishedFileService/QueryFiles/v1/?" + urllib.parse.urlencode(q))
    try:
        r = json.loads(raw)["response"]
    except (ValueError, KeyError) as e:
        raise WorkshopError("bad API answer (key?)") from e
    total = int(r.get("total") or 0)
    items = [_item(d) for d in r.get("publishedfiledetails") or [] if d.get("result", 1) == 1]
    return {"items": items, "total": total, "page": page, "pages": max(1, -(-total // PER_PAGE))}


def details(ids: list[str], key: str = "") -> list[dict]:
    if not ids:
        return []
    if key:     # avec clé : on a aussi la note (votes)
        q = [("key", key), ("includetags", "true"), ("includevotes", "true")]
        q += [(f"publishedfileids[{i}]", v) for i, v in enumerate(ids)]
        try:
            files = json.loads(_get("https://api.steampowered.com/IPublishedFileService/GetDetails/v1/?"
                                    + urllib.parse.urlencode(q)))["response"]["publishedfiledetails"]
            by_id = {f.get("publishedfileid"): f for f in files if f.get("result") == 1}
            return [_item(by_id[i]) for i in ids if i in by_id]
        except (WorkshopError, ValueError, KeyError):
            pass                                  # clé refusée : on fait sans
    data = {"itemcount": str(len(ids))}
    data.update({f"publishedfileids[{i}]": v for i, v in enumerate(ids)})
    try:
        d = json.loads(_get("https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/", data))
        files = d["response"]["publishedfiledetails"]
    except (ValueError, KeyError) as e:
        raise WorkshopError("bad API answer") from e
    by_id = {f.get("publishedfileid"): f for f in files if f.get("result") == 1}
    return [_item(by_id[i]) for i in ids if i in by_id]


def _item(d: dict) -> dict:
    tags = [t.get("tag", "") for t in d.get("tags") or []]
    kind = next((t for t in tags if t in TYPES), "")
    preview = d.get("preview_url") or ""
    if preview and "?" not in preview:
        preview += "?imw=480&imh=270&ima=fit&impolicy=Letterbox"
    votes = d.get("vote_data") or {}
    return {
        "id": str(d.get("publishedfileid", "")),
        "title": d.get("title") or "?",
        "preview": preview,
        "type": kind.lower(),
        "rating": next((t for t in tags if t in RATINGS), ""),
        "tags": [t for t in tags if t not in TYPES and t not in RATINGS and t not in NOISE_TAGS
                 and not RES_TAG.match(t)],
        "resolution": next((t for t in tags if RES_TAG.match(t)), ""),
        "approved": "Approved" in tags,
        "size": int(d.get("file_size") or 0),
        "subs": int(d.get("lifetime_subscriptions") or d.get("subscriptions") or 0),
        "favorited": int(d.get("lifetime_favorited") or d.get("favorited") or 0),
        "views": int(d.get("views") or 0),
        "score": float(votes.get("score") or 0),
        "created": int(d.get("time_created") or 0),
        "updated": int(d.get("time_updated") or 0),
    }


def details_many(ids: list[str], key: str = "", chunk: int = 50) -> dict:
    """{id: item} pour beaucoup d'identifiants (par paquets)."""
    out = {}
    for i in range(0, len(ids), chunk):
        for it in details(ids[i:i + chunk], key):
            out[it["id"]] = it
    return out


def page_url(wid: str) -> str:
    """Page du fond dans le client Steam (bouton « S'abonner »)."""
    return f"steam://url/CommunityFilePage/{wid}"
