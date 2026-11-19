#!/usr/bin/env python3
"""Build roman-roads-fr.json from the Itiner-e export (https://www.itiner-e.org, CC BY 4.0).

Downloads the full export (one JSON road segment per line), keeps the land roads that
touch metropolitan France, simplifies them and writes a compact file the app can load.
"""
import json, sys, urllib.request

URL = "https://www.itiner-e.org/route-segments/download"
OUT = "roman-roads-fr.json"
WEST, SOUTH, EAST, NORTH = -5.3, 41.2, 9.7, 51.3
TOL = 0.00008          # about 8 m


def simplify(pts, tol):
    """Douglas-Peucker on [lon, lat] points (iterative)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a][0], pts[a][1]
        bx, by = pts[b][0], pts[b][1]
        dx, dy = bx - ax, by - ay
        norm = dx * dx + dy * dy
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i][0] - ax, pts[i][1] - ay
            if norm == 0:
                d = px * px + py * py
            else:
                t = max(0.0, min(1.0, (px * dx + py * dy) / norm))
                ex, ey = px - t * dx, py - t * dy
                d = ex * ex + ey * ey
            if d > best:
                best, idx = d, i
        if idx >= 0 and best > tol * tol:
            keep[idx] = True
            stack.append((a, idx))
            stack.append((idx, b))
    return [p for p, k in zip(pts, keep) if k]


def lines_of(geom):
    if not isinstance(geom, dict):
        return []
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return c
    return []


def pick(props, *names):
    for n in names:
        v = props.get(n)
        if isinstance(v, (str, int, float)) and str(v).strip():
            return str(v).strip()
    return ""


def main():
    roads, seen_keys, total, kept_types = [], set(), 0, {}
    req = urllib.request.Request(URL, headers={"User-Agent": "cassini-overlay build script"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            raw = raw.strip().rstrip(b",")
            if not raw or raw in (b"[", b"]"):
                continue
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            total += 1
            props = obj.get("properties") if isinstance(obj.get("properties"), dict) else obj
            geom = obj.get("geometry") if isinstance(obj.get("geometry"), dict) else obj
            seen_keys.update(k for k in props.keys() if k not in ("coordinates", "pleiadesPlaces"))
            kind = pick(props, "type", "roadType", "segmentType")
            if kind in ("LineString", "MultiLineString", "Feature"):
                kind = pick(props, "roadType", "segmentType")
            if any(w in kind.lower() for w in ("river", "sea", "lake", "maritime")):
                continue
            for line in lines_of(geom):
                pts = [p for p in line if isinstance(p, list) and len(p) >= 2]
                if len(pts) < 2:
                    continue
                if not any(WEST <= p[0] <= EAST and SOUTH <= p[1] <= NORTH for p in pts):
                    continue
                pts = simplify(pts, TOL)
                roads.append({
                    "n": pick(props, "name", "title", "label"),
                    "t": kind,
                    "c": pick(props, "segmentCertainty", "certainty", "locationCertainty", "confidence"),
                    "l": [[round(p[1], 5), round(p[0], 5)] for p in pts],
                })
                kept_types[kind] = kept_types.get(kind, 0) + 1
    if not roads:
        sys.exit("No road kept out of %d segments - export format may have changed" % total)
    meta = {"source": "Itiner-e (itiner-e.org), CC BY 4.0", "segments_read": total,
            "segments_kept": len(roads), "types": kept_types, "property_keys": sorted(seen_keys)}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "roads": roads}, f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
