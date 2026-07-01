#!/usr/bin/env python3
"""OSM Overpass nearby search — find amenities around a coordinate.

Usage: osm_nearby.py <lat> <lng> [radius_km=3] [amenity=restaurant] [name_pattern]

name_pattern — optional case-insensitive regex filtered locally on name.
Example: 'Pizza|Italian' matches either.
"""
import sys, json, math, re, urllib.parse, urllib.request


def haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    if len(sys.argv) < 3:
        print("usage: osm_nearby.py <lat> <lng> [radius_km=3] [amenity=restaurant] [name_pattern]", file=sys.stderr)
        sys.exit(2)

    lat = float(sys.argv[1])
    lng = float(sys.argv[2])
    radius_km = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    amenity = sys.argv[4] if len(sys.argv) > 4 else "restaurant"
    name_pattern = sys.argv[5] if len(sys.argv) > 5 else None
    radius_m = int(radius_km * 1000)

    name_re = None
    if name_pattern:
        try:
            name_re = re.compile(name_pattern, re.IGNORECASE)
        except re.error as e:
            print(f"ERROR: invalid name regex: {e}", file=sys.stderr)
            sys.exit(2)

    query = (
        "[out:json][timeout:30];"
        "("
        f'node["amenity"="{amenity}"](around:{radius_m},{lat},{lng});'
        f'way["amenity"="{amenity}"](around:{radius_m},{lat},{lng});'
        ");"
        "out body center 100;"
    )
    url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(query)

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "claude-code-methodology/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as e:
        print(f"ERROR: Overpass request failed: {e}", file=sys.stderr)
        sys.exit(1)

    elements = data.get("elements", [])
    results = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name", "")
        if not name:
            continue
        if name_re and not name_re.search(name):
            continue
        el_lat = el.get("lat") or el.get("center", {}).get("lat")
        el_lng = el.get("lon") or el.get("center", {}).get("lon")
        if not el_lat or not el_lng:
            continue
        distance = int(haversine(lat, lng, el_lat, el_lng))

        addr_parts = []
        if tags.get("addr:street"):
            addr_parts.append(tags["addr:street"])
        if tags.get("addr:housenumber"):
            addr_parts.append(tags["addr:housenumber"])
        city = tags.get("addr:city") or tags.get("addr:suburb") or ""

        results.append({
            "name": name,
            "cuisine": tags.get("cuisine", "").replace(";", ", "),
            "address": ", ".join(addr_parts),
            "city": city,
            "distance_m": distance,
            "website": tags.get("website") or tags.get("contact:website", ""),
            "phone": tags.get("phone") or tags.get("contact:phone", ""),
            "opening_hours": tags.get("opening_hours", ""),
            "lat": el_lat,
            "lng": el_lng,
        })

    results.sort(key=lambda x: x["distance_m"])

    if not results:
        print(f"No '{amenity}' found within {radius_km} km of {lat:.5f},{lng:.5f}")
        return

    print(f"Found {len(results)} '{amenity}' within {radius_km} km of {lat:.5f},{lng:.5f}")
    print(f"(showing top {min(20, len(results))} sorted by distance)\n")

    for r in results[:20]:
        d = r["distance_m"]
        dist_str = f"{d}m" if d < 1000 else f"{d/1000:.1f}km"
        line = f"[{dist_str}] {r['name']}"
        if r["cuisine"]:
            line += f" — {r['cuisine']}"
        print(line)
        extras = []
        if r["address"]:
            addr = r["address"]
            if r["city"]:
                addr += f", {r['city']}"
            extras.append(f"addr: {addr}")
        elif r["city"]:
            extras.append(f"addr: {r['city']}")
        if r["phone"]:
            extras.append(f"tel: {r['phone']}")
        if r["website"]:
            extras.append(f"web: {r['website']}")
        if r["opening_hours"]:
            extras.append(f"hours: {r['opening_hours']}")
        extras.append(f"maps: https://www.google.com/maps?q={r['lat']},{r['lng']}")
        for e in extras:
            print(f"   {e}")
        print()


if __name__ == "__main__":
    main()
