#!/usr/bin/env bash
# OSM Overpass nearby search — find amenities (restaurants/cafes/pharmacies/etc)
# near a coordinate. Free, no registration. OpenStreetMap data.
#
# Usage:
#   osm-nearby.sh <lat> <lng> [radius_km=3] [amenity=restaurant] [name_regex]
#
# Examples:
#   osm-nearby.sh 50.3490 30.3820 5 restaurant
#   osm-nearby.sh 50.4501 30.5234 2 cafe
#   osm-nearby.sh 50.4501 30.5234 5 restaurant "Pizza|Italian"
#
# Common amenities: restaurant, cafe, fast_food, bar, pub, pharmacy, atm,
#                   bank, fuel, hospital, school

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -lt 2 ]]; then
  echo "usage: osm-nearby.sh <lat> <lng> [radius_km=3] [amenity=restaurant] [name_regex]" >&2
  exit 2
fi

exec python3 "$SCRIPT_DIR/osm_nearby.py" "$@"
