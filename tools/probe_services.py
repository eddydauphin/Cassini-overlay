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
    cors = next((v for k, v in h.items() if k.lower() == "access-control-allow-origin"), "-")
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

    line()
    line("# Round 2: Estonian scale limits, heritage filter, French place-name types")
    st, h, b = get("https://kaart.maaamet.ee/wms/ajalooline?service=WMS&version=1.1.1&request=GetCapabilities", 30_000_000)
    x = b.decode("utf-8", "replace")
    for name in ("yheverstakaart", "yheverstakaart_alt", "kolmeverstakaart", "kolmeverstakaart_alt", "kaheverstakaart", "Halduspiir_raster",
                 "ew_50T", "ew_25T", "ew_200T", "nltopo_vanem_25T", "nltopo_vanem_25T_alt", "nltopo_vanem_50T", "kk1940", "reljeef2020", "TOPOYKSUS_6569"):
        m = re.search(r"<Layer[^>]*>\s*<Name>%s</Name>.*?</Layer>" % re.escape(name), x, re.S)
        hint = re.search(r"<ScaleHint[^>]*/>", m.group(0)) if m else None
        line("   %-24s %s" % (name, hint.group(0) if hint else ("no ScaleHint" if m else "NOT FOUND")))
    # same 256px image at four ground resolutions around Tallinn (EPSG:3301): 2, 5, 12, 40 m per pixel
    for layer in ("yheverstakaart", "yheverstakaart_alt", "yheverstakaart_alt,yheverstakaart", "kolmeverstakaart", "kolmeverstakaart_alt",
                  "Halduspiir_raster", "ew_50T", "ew_25T", "nltopo_vanem_25T", "nltopo_vanem_25T_alt", "kk1940", "reljeef2020", "TOPOYKSUS_6569"):
        sizes = []
        for res in (2, 5, 12, 40):
            half = res * 128
            st, h, b = get("https://kaart.maaamet.ee/wms/ajalooline?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=%s&STYLES=&FORMAT=image/png"
                           "&SRS=EPSG:3301&WIDTH=256&HEIGHT=256&BBOX=%d,%d,%d,%d" % (layer, 552000 - half, 6580000 - half, 552000 + half, 6580000 + half))
            ct = next((v for k, v in h.items() if k.lower() == "content-type"), "?")
            sizes.append("%sm/px:%s%d" % (res, "" if ct.startswith("image") else "ERR ", len(b)))
        line("   %-36s %s" % (layer, "  ".join(sizes)))
    cql = "BBOX(geom,24.2,59.2,25.4,59.7,'EPSG:4326') AND tyyp <> 'KPO_LIIK_EHITISMALESTIS'"
    st, h, b = head("heritage cql non-buildings", "https://gsavalik.envir.ee/geoserver/muinsuskaitse/ows?service=WFS&version=1.1.0&request=GetFeature"
                    "&typeName=muinsuskaitse:kpo_malestised&srsName=EPSG:4326&maxFeatures=400&outputFormat=application/json&cql_filter=" + urllib.parse.quote(cql))
    try:
        d = json.loads(b)
        fs = d.get("features", [])
        line("   features: %d" % len(fs))
        kinds = {}
        for f in fs:
            k = (f["properties"].get("tyyp"), f["properties"].get("tyyp_nimi"), (f.get("geometry") or {}).get("type"))
            kinds[k] = kinds.get(k, 0) + 1
        line("   kinds: %s" % kinds)
        for f in fs[:12]:
            line("   - %s | %s" % (f["properties"].get("tyyp_nimi"), f["properties"].get("nimi")))
    except Exception as e:  # noqa
        line("   not JSON: %s" % e)
    st, h, b = get("https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities", 60_000_000)
    x = b.decode("utf-8", "replace")
    names = re.findall(r"<Name>(BDTOPO_V3:[^<]+)</Name>", x)
    line("   BDTOPO_V3 types with topony/lieu/zone/detail: " + " ".join(n for n in names if re.search(r"topony|lieu|zone_d|detail|construction_p", n)))
    head("geopf wfs CORS check", "https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=BDTOPO_V3:lieu_dit_non_habite"
         "&OUTPUTFORMAT=application/json&SRSNAME=EPSG:4326&COUNT=1&BBOX=50.30,1.95,50.47,2.12,urn:ogc:def:crs:EPSG::4326")

    line()
    line("# Round 3: exact requests the app sends over Estonia")
    cql = ("BBOX(geom,24.70056,59.38108,24.80658,59.49280,'EPSG:4326') AND (tyyp <> 'KPO_LIIK_EHITISMALESTIS' OR nimi ILIKE '%linnus%' "
           "OR nimi ILIKE '%kindlus%' OR nimi ILIKE '%mõisa peahoone%' OR nimi ILIKE '%patarei%')")
    st, h, b = head("heritage app query", "https://gsavalik.envir.ee/geoserver/muinsuskaitse/ows?service=WFS&version=1.1.0&request=GetFeature"
                    "&typeName=muinsuskaitse:kpo_malestised&srsName=EPSG:4326&maxFeatures=2000&outputFormat=application/json&cql_filter=" + urllib.parse.quote(cql))
    try:
        fs = json.loads(b).get("features", [])
        line("   features: %d ; sample: %s" % (len(fs), " | ".join(str(f["properties"].get("nimi")) for f in fs[:14])))
    except Exception as e:  # noqa
        line("   not JSON: %s" % e)
    for layer, extra in (("reljeef2020", ""), ("yheverstakaart_alt", ""), ("TOPOYKSUS_6569", "&TRANSPARENT=TRUE")):
        head("app tile " + layer, "https://kaart.maaamet.ee/wms/ajalooline?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&STYLES=&SRS=EPSG:3301&LAYERS=" + layer +
             "&FORMAT=image/png" + extra + "&WIDTH=320&HEIGHT=319&BBOX=542682.00,6589002.00,542840.00,6589159.00")
    st, h, b = head("geopf wfs toponymie", "https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=BDTOPO_V3:toponymie"
                    "&OUTPUTFORMAT=application/json&SRSNAME=EPSG:4326&COUNT=3&BBOX=50.30,1.95,50.47,2.12,urn:ogc:def:crs:EPSG::4326")
    try:
        for f in json.loads(b).get("features", [])[:2]:
            line("   geom=%s props=%s" % (json.dumps(f.get("geometry"))[:100], json.dumps(f.get("properties"), ensure_ascii=False)[:420]))
    except Exception as e:  # noqa
        line("   not JSON: %s" % e)

    line()
    line("# Round 4: French heritage register (Monuments historiques, data.culture.gouv.fr)")
    api = "https://data.culture.gouv.fr/api/explore/v2.1/catalog/datasets"
    st, h, b = head("culture catalog search", api + "?limit=30&select=dataset_id,records_count&where=" + urllib.parse.quote('search("monuments historiques") or search("merimee") or search("archeologi")'))
    try:
        line("   datasets: " + " ; ".join("%s (%s)" % (r.get("dataset_id"), r.get("records_count")) for r in json.loads(b).get("results", [])))
    except Exception as e:  # noqa
        line("   not JSON: %s" % e)
    ds = "liste-des-immeubles-proteges-au-titre-des-monuments-historiques"
    st, h, b = head("MH dataset meta", api + "/" + ds)
    try:
        d = json.loads(b)
        line("   fields: " + " ; ".join("%s[%s]" % (f.get("name"), f.get("type")) for f in d.get("fields", [])))
    except Exception as e:  # noqa
        line("   not JSON: %s" % e)
    st, h, b = head("MH records sample", api + "/" + ds + "/records?limit=2")
    try:
        for r in json.loads(b).get("results", [])[:2]:
            line("   " + json.dumps(r, ensure_ascii=False)[:1800])
    except Exception as e:  # noqa
        line("   not JSON: %s" % e)

    os.makedirs("diag", exist_ok=True)
    with open("diag/probe.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")


if __name__ == "__main__":
    main()
