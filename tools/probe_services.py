#!/usr/bin/env python3
"""Check the public map services the app relies on and write what they answer to diag/probe.txt.

Run by a GitHub Action because the services cannot be reached from the development sandbox.
Read-only: it only downloads small public responses.
"""
import json, os, re, urllib.parse, urllib.request

OUT = []
ORIGIN = "https://cassini-overlay.vercel.app"


def get(url, limit=3_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": "cassini-overlay probe", "Origin": ORIGIN})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read(limit)
            return r.status, dict(r.headers), body
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(20000)
    except Exception as e:  # noqa
        return 0, {}, str(e).encode()


def line(s=""):
    OUT.append(s)
    print(s)


def head(title, url):
    st, h, b = get(url)
    ct = h.get("Content-Type", "?")
    cors = h.get("Access-Control-Allow-Origin", "-")
    text = ""
    if not ct.startswith("image"):
        text = b[:400].decode("utf-8", "replace").replace("\n", " ")
    line("%-34s HTTP %s | %s | %d bytes | CORS %s | %s" % (title, st, ct, len(b), cors, text[:260]))
    return st, h, b


def caps(title, url):
    st, h, b = get(url, 30_000_000)
    x = b.decode("utf-8", "replace")
    names = re.findall(r"<Layer[^>]*>\s*<Name>([^<]+)</Name>\s*<Title>([^<]*)</Title>", x)
    srs = sorted(set(re.findall(r"<(?:SRS|CRS)>([^<]+)</(?:SRS|CRS)>", x)))
    line("== %s: HTTP %s, %d layers" % (title, st, len(names)))
    line("   SRS: " + " ".join(srs)[:600])
    return names, x


def main():
    line("# Estonia: WMS capabilities")
    for svc in ("ajalooline", "alus-geo", "fotokaart", "alus"):
        names, x = caps(svc, "https://kaart.maaamet.ee/wms/%s?service=WMS&version=1.1.1&request=GetCapabilities" % svc)
        keep = [n for n in names if not re.match(r"(of\d|HYB_|pk_|.*_info$)", n[0])] if svc == "ajalooline" else names
        for n, t in keep[:140]:
            line("   %s | %s" % (n, t))
        if svc == "ajalooline":
            m = re.search(r"<Layer[^>]*>\s*<Name>reljeef2020</Name>.*?</Layer>", x, re.S)
            line("   reljeef2020 block: " + (re.sub(r"\s+", " ", m.group(0))[:700] if m else "NOT FOUND"))
            m = re.search(r"<Layer[^>]*>\s*<Name>yheverstakaart</Name>.*?</Layer>", x, re.S)
            line("   yheverstakaart block: " + (re.sub(r"\s+", " ", m.group(0))[:700] if m else "NOT FOUND"))

    line()
    line("# Estonia: GetMap in three projections (Tallinn area)")
    boxes = {"EPSG:3857": "2749000,8265000,2762000,8278000", "EPSG:4326": "24.70,59.40,24.82,59.46",
             "EPSG:3301": "540000,6585000,548000,6593000"}
    for svc, layer in (("ajalooline", "reljeef2020"), ("ajalooline", "yheverstakaart"), ("ajalooline", "ew_50T"),
                       ("ajalooline", "TOPOYKSUS_6569"), ("alus-geo", "reljeef"), ("alus-geo", "of10000"),
                       ("fotokaart", "EESTIFOTO")):
        for srs, box in boxes.items():
            head("%s/%s %s" % (svc, layer, srs),
                 "https://kaart.maaamet.ee/wms/%s?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=%s&STYLES=&FORMAT=image/png"
                 "&SRS=%s&WIDTH=256&HEIGHT=256&BBOX=%s" % (svc, layer, srs, box))

    line()
    line("# Estonia: tile services")
    head("tms foto@GMC z13", "https://tiles.maaamet.ee/tm/tms/1.0.0/foto@GMC/13/4660/5791.png")
    head("tms kaart@GMC z13", "https://tiles.maaamet.ee/tm/tms/1.0.0/kaart@GMC/13/4660/5791.png")
    for cand in ("vreljeef", "reljeef", "hybriid", "fotokaart", "epk_vv", "ajalooline"):
        head("tms %s@GMC z13" % cand, "https://tiles.maaamet.ee/tm/tms/1.0.0/%s@GMC/13/4660/5791.png" % cand)
    st, h, b = get("https://tiles.maaamet.ee/tm/tms/1.0.0/")
    line("tms root: HTTP %s | %s" % (st, " ".join(re.findall(r'title="([^"]+)"|href="[^"]*/1\.0\.0/([^"/]+)', b.decode("utf-8", "replace"))[i][1]
                                                    for i in range(min(80, len(re.findall(r'href="[^"]*/1\.0\.0/([^"/]+)', b.decode("utf-8", "replace"))))))[:1500]))
    st, h, b = get("https://tiles.maaamet.ee/tm/wmts/1.0.0/WMTSCapabilities.xml", 30_000_000)
    x = b.decode("utf-8", "replace")
    line("wmts caps: HTTP %s | layers: %s" % (st, " ".join(sorted(set(re.findall(r"<ows:Identifier>([^<]+)</ows:Identifier>", x))))[:2500]))

    line()
    line("# Estonia: heritage register WFS")
    base = ("https://gsavalik.envir.ee/geoserver/muinsuskaitse/ows?service=WFS&version=1.1.0&request=GetFeature"
            "&typeName=muinsuskaitse:kpo_malestised&srsName=EPSG:4326&maxFeatures=3&outputFormat=application/json")
    for label, box in (("lonlat EPSG:4326", "24.60,59.35,24.95,59.50,EPSG:4326"),
                       ("latlon urn", "59.35,24.60,59.50,24.95,urn:ogc:def:crs:EPSG::4326")):
        st, h, b = head("heritage " + label, base + "&bbox=" + box)
        try:
            d = json.loads(b)
            line("   features: %d" % len(d.get("features", [])))
            for f in d.get("features", [])[:2]:
                g = f.get("geometry") or {}
                c = g.get("coordinates")
                while isinstance(c, list) and c and isinstance(c[0], list):
                    c = c[0]
                line("   id=%s geom=%s first=%s props=%s" % (f.get("id"), g.get("type"), c, json.dumps(f.get("properties"), ensure_ascii=False)[:900]))
        except Exception as e:  # noqa
            line("   not JSON: %s" % e)
    st, h, b = get("https://gsavalik.envir.ee/geoserver/muinsuskaitse/ows?service=WFS&version=1.1.0&request=GetCapabilities")
    line("   muinsuskaitse feature types: " + " ".join(re.findall(r"<Name>(muinsuskaitse:[^<]+)</Name>", b.decode("utf-8", "replace"))))

    line()
    line("# France: services never verified live")
    geopf = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&TILEMATRIXSET=PM&TILEMATRIX=14&TILEROW=5527&TILECOL=8285"
    for label, q in (("cassini png", "&LAYER=BNF-IGNF_GEOGRAPHICALGRIDSYSTEMS.CASSINI&STYLE=normal&FORMAT=image/png"),
                     ("cassini jpeg", "&LAYER=BNF-IGNF_GEOGRAPHICALGRIDSYSTEMS.CASSINI&STYLE=normal&FORMAT=image/jpeg"),
                     ("ortho", "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg"),
                     ("lidar hd shadow normal", "&LAYER=IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW&STYLE=normal&FORMAT=image/png"),
                     ("old shadow estompage", "&LAYER=ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW&STYLE=estompage_grayscale&FORMAT=image/png"),
                     ("cadastre PCI", "&LAYER=CADASTRALPARCELS.PARCELLAIRE_EXPRESS&STYLE=" + urllib.parse.quote("PCI vecteur") + "&FORMAT=image/png")):
        head("geopf " + label, geopf + q)
    st, h, b = get("https://data.geopf.fr/wmts?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetCapabilities", 60_000_000)
    x = b.decode("utf-8", "replace")
    ids = sorted(set(re.findall(r"<ows:Identifier>([^<]+)</ows:Identifier>", x)))
    line("geopf wmts ids matching CASSINI/LIDAR/SHADOW/PARCEL: " + " ".join(i for i in ids if re.search(r"CASSINI|LIDAR|SHADOW|PARCEL|ETATMAJOR", i))[:3000])
    for m in re.finditer(r"<Layer>.*?</Layer>", x, re.S):
        blk = m.group(0)
        if re.search(r"<ows:Identifier>[^<]*(LIDAR-HD_MNT[^<]*SHADOW|CASSINI|PARCELLAIRE_EXPRESS)</ows:Identifier>", blk):
            line("   " + re.sub(r"\s+", " ", " ".join(re.findall(r"<ows:Identifier>[^<]+</ows:Identifier>|<Format>[^<]+</Format>|<TileMatrix>[^<]+</TileMatrix>", blk)))[:900])
    for t in ("BDTOPO_V3:lieu_dit_non_habite", "BDTOPO_V3:toponymie_lieux_nommes"):
        st, h, b = head("geopf wfs " + t, "https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=" + t +
                        "&OUTPUTFORMAT=application/json&SRSNAME=EPSG:4326&COUNT=2&BBOX=50.30,1.95,50.47,2.12,urn:ogc:def:crs:EPSG::4326")
        try:
            d = json.loads(b)
            for f in d.get("features", [])[:1]:
                line("   geom=%s props=%s" % (json.dumps(f.get("geometry"))[:120], json.dumps(f.get("properties"), ensure_ascii=False)[:500]))
        except Exception as e:  # noqa
            line("   not JSON: %s" % e)
    q = '[out:json][timeout:25];(nwr["historic"~"^(castle|battlefield)$"](50.30,1.95,50.47,2.12););out center tags 5;'
    head("overpass", "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(q))
    head("wikipedia fr geosearch", "https://fr.wikipedia.org/w/api.php?action=query&list=geosearch&gscoord=50.46%7C2.13&gsradius=10000&gslimit=5&format=json&origin=*")
    sparql = ('SELECT ?item ?itemLabel WHERE { SERVICE wikibase:box { ?item wdt:P625 ?loc. bd:serviceParam wikibase:cornerSouthWest '
              '"Point(1.9 50.25)"^^geo:wktLiteral; wikibase:cornerNorthEast "Point(2.3 50.55)"^^geo:wktLiteral. } VALUES ?cls { wd:Q178561 wd:Q188055 } '
              '?item wdt:P31/wdt:P279* ?cls. SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" } } LIMIT 20')
    head("wikidata battles", "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(sparql))

    os.makedirs("diag", exist_ok=True)
    with open("diag/probe.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
