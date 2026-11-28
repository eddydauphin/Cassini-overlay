#!/usr/bin/env python3
"""Build monuments-fr.json from the French Ministry of Culture open data
"Immeubles protégés au titre des Monuments Historiques" (base Mérimée, Licence Ouverte 2.0),
published on data.gouv.fr. Keeps the kinds of monuments useful for field history
(castles, mottes, forts, archaeological sites, abbeys, mills...) and drops ordinary buildings.
"""
import csv, io, json, re, sys, unicodedata, urllib.request

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


def main():
    meta = json.loads(urllib.request.urlopen(urllib.request.Request(DATASET, headers={"User-Agent": "cassini-overlay build script"}), timeout=120).read())
    res = [r for r in meta.get("resources", []) if "csv" in (str(r.get("format")) + str(r.get("title"))).lower()]
    if not res:
        sys.exit("No CSV resource found: %s" % [(r.get("title"), r.get("format")) for r in meta.get("resources", [])])
    url = res[0]["url"]
    print("downloading", res[0].get("title"), url, res[0].get("filesize"))
    csv.field_size_limit(50_000_000)
    req = urllib.request.Request(url, headers={"User-Agent": "cassini-overlay build script"})
    out, cats, nogeo, denoms, total, coord_samples = [], {}, 0, {}, 0, []
    with urllib.request.urlopen(req, timeout=900) as resp:
        rows = csv.DictReader(io.TextIOWrapper(resp, encoding="utf-8", newline=""), delimiter="|", quotechar='"')
        for p in rows:
            total += 1
            g = lambda k: (p.get(k) or "").strip()
            denom, title = g("Denomination_de_l_edifice"), g("Titre_editorial_de_la_notice")
            for d in denom.split(";"):
                d = d.strip()[:40]
                denoms[d] = denoms.get(d, 0) + 1
            w = g("coordonnees_au_format_WGS84")
            if w and len(coord_samples) < 4:
                coord_samples.append(w)
            m = re.match(r"\s*\[?\s*(-?\d+(?:\.\d+)?)\s*[,; ]\s*(-?\d+(?:\.\d+)?)", w)
            if not m:
                nogeo += 1
                continue
            lat, lon = float(m.group(1)), float(m.group(2))
            if not (41 < lat < 51.6 and -5.6 < lon < 10):
                if 41 < lon < 51.6 and -5.6 < lat < 10:
                    lat, lon = lon, lat
                else:
                    nogeo += 1
                    continue
            pd = plain(denom)
            cat = next((c for c, rx in RULES if re.search(rx, pd)), None) or next((c for c, rx in RULES if re.search(rx, plain(title))), None)
            if not cat:
                continue
            if cat in ("castle", "other") and re.search(r"^(eglise|maison|hotel|immeuble|chapelle|presbytere|cathedrale)\b", pd) \
                    and not re.search(r"chateau|manoir|motte|abbaye|prieure|commanderie", pd):
                continue
            out.append({"r": g("Reference"), "n": (title or denom)[:110], "d": denom[:60], "k": cat,
                        "c": (g("Commune_forme_editoriale") or g("Commune_forme_index"))[:40],
                        "s": g("Siecle_de_la_campagne_principale_de_construction")[:60],
                        "p": g("Date_et_typologie_de_la_protection")[:70],
                        "y": round(lat, 5), "x": round(lon, 5)})
            cats[cat] = cats.get(cat, 0) + 1
    if len(out) < 1000:
        sys.exit("Only %d monuments kept out of %d (no position: %d) - format may have changed; coords like %s" % (len(out), total, nogeo, coord_samples))
    info = {"source": "Ministère de la Culture, base Mérimée (Monuments historiques), Licence Ouverte 2.0",
            "read": total, "kept": len(out), "without_position": nogeo, "categories": cats, "coord_samples": coord_samples,
            "top_denominations": sorted(denoms.items(), key=lambda kv: -kv[1])[:80], "samples": out[:6]}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"meta": info, "sites": out}, fh, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(info, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
