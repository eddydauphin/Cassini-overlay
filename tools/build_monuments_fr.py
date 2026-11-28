#!/usr/bin/env python3
"""Build monuments-fr.json from the French Ministry of Culture open data
"Immeubles protégés au titre des Monuments Historiques" (base Mérimée, Licence Ouverte 2.0),
published on data.gouv.fr. Keeps the kinds of monuments useful for field history
(castles, mottes, forts, archaeological sites, abbeys, mills...) and drops ordinary buildings.
"""
import json, re, sys, unicodedata, urllib.request

DATASET = "https://www.data.gouv.fr/api/1/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2/"
OUT = "monuments-fr.json"

RULES = [  # (category, regex on the accent-free lower-case denomination + title)
    ("battle", r"champ de bataille|lieu de bataille"),
    ("arch", r"site archeologique|dolmen|menhir|tumulus|oppidum|allee couverte|cromlech|polissoir|necropole|grotte|abri sous roche|eperon barre"
             r"|borne milliaire|fanum|villa\b|thermes|amphitheatre|theatre antique|aqueduc|voie romaine|voie antique|camp romain|camp protohistorique"
             r"|camp prehistorique|enceinte prehistorique|enceinte protohistorique|cimetiere merovingien|sarcophage|gallo-romain|gallo romain|vestiges antiques|pierre a cupules|megalith"),
    ("milit", r"\bfort\b|fortin|citadelle|batterie|blockhaus|casemate|redoute|ouvrage fortifie|ouvrage militaire|poudriere|arsenal|bunker|base de lancement"
              r"|ligne fortifiee|caserne|camp militaire|camp retranche|tranchee|abri militaire|corps de garde|lunette|bastion"),
    ("castle", r"chateau|manoir|motte|donjon|maison forte|enceinte|rempart|fortification|porte de ville|tour\b|castrum|bastide|ferme fortifiee|gentilhommiere"),
    ("other", r"abbaye|prieure|commanderie|chartreuse|couvent|monastere|ermitage|leproserie|maladrerie|moulin|forge|templier|hopital|hospice|ruines|vestiges"),
]


def plain(s):
    s = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("-", " ").replace("’", "'")


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cassini-overlay build script"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode("utf-8"))


def first(props, patterns):
    for pat in patterns:
        for k, v in props.items():
            if re.search(pat, k, re.I) and v not in (None, "", []):
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v)
                return str(v).strip()
    return ""


def main():
    meta = get_json(DATASET)
    res = [r for r in meta.get("resources", []) if "geojson" in (str(r.get("format")) + str(r.get("title")) + str(r.get("url"))).lower()]
    if not res:
        sys.exit("No GeoJSON resource found: %s" % [(r.get("title"), r.get("format")) for r in meta.get("resources", [])])
    url = res[0].get("latest") or res[0]["url"]
    print("downloading", res[0].get("title"), url, res[0].get("filesize"))
    data = get_json(url)
    feats = data.get("features", [])
    keys, out, cats, nogeo, denoms = {}, [], {}, 0, {}
    for f in feats:
        p = f.get("properties") or {}
        for k in p:
            keys[k] = keys.get(k, 0) + 1
        g = f.get("geometry") or {}
        c = g.get("coordinates")
        lon = lat = None
        if g.get("type") == "Point" and isinstance(c, list) and len(c) >= 2:
            lon, lat = c[0], c[1]
        else:
            w = first(p, [r"wgs84", r"coordonnees", r"geoloc", r"geo_point"])
            m = re.match(r"\s*\[?\s*(-?\d+\.\d+)\s*[,; ]\s*(-?\d+\.\d+)", w)
            if m:
                lat, lon = float(m.group(1)), float(m.group(2))
        denom = first(p, [r"^denomination"])
        title = first(p, [r"titre_editorial", r"^titre", r"appellation"])
        denoms[denom[:40]] = denoms.get(denom[:40], 0) + 1
        if lat is None or not (41 < lat < 51.6 and -5.6 < lon < 10):
            nogeo += 1
            continue
        text = plain(denom + " | " + title)
        cat = next((c for c, rx in RULES if re.search(rx, text)), None)
        if not cat:
            continue
        if cat in ("castle", "other") and re.search(r"^(eglise|maison|hotel|immeuble|chapelle)\b", plain(denom)) and not re.search(r"chateau|manoir|motte|abbaye|prieure|commanderie", plain(denom)):
            continue
        ref = first(p, [r"^reference$", r"^ref$", r"reference"])
        out.append({"r": ref, "n": (title or denom)[:110], "d": denom[:60], "k": cat,
                    "c": first(p, [r"^commune_forme_index", r"^commune"])[:40],
                    "s": first(p, [r"siecle.*principale", r"^siecle", r"datation"])[:60],
                    "p": first(p, [r"typologie_de_la_protection", r"nature_de_la_protection", r"protection"])[:60],
                    "y": round(lat, 5), "x": round(lon, 5)})
        cats[cat] = cats.get(cat, 0) + 1
    if len(out) < 1000:
        print("property keys:", sorted(keys))
        sys.exit("Only %d monuments kept out of %d - field names may have changed" % (len(out), len(feats)))
    info = {"source": "Ministère de la Culture, base Mérimée (Monuments historiques), Licence Ouverte 2.0",
            "read": len(feats), "kept": len(out), "without_position": nogeo, "categories": cats,
            "property_keys": sorted(keys), "top_denominations": sorted(denoms.items(), key=lambda kv: -kv[1])[:60],
            "samples": out[:6]}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"meta": info, "sites": out}, fh, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(info, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
