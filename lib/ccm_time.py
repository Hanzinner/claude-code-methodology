#!/usr/bin/env python3
"""The time zone named in CCM_TIMEZONE, also where Python has no zone database.

    import ccm_time
    tz = ccm_time.zone(conf("CCM_TIMEZONE", ""))   # tzinfo, or None = the system's local zone
    datetime.now(tz); datetime.fromtimestamp(ts, tz); dt.astimezone(tz)     # all accept None

zoneinfo reads the IANA database from the system (Linux, macOS) or from the `tzdata` package. Python from python.org on
Windows has neither unless `python -m pip install tzdata` was run, and ZoneInfo("Europe/Kyiv") raises
ZoneInfoNotFoundError: a script that built its zone at import died before doing anything. Here a name that can't be
loaded (no database, or a typo) gives None - the system's local zone, which on a machine set to the human's own zone is
the same clock - and ONE warning on stderr saying how to get the real one. UTC needs no database.
"""
import datetime
import sys

_UTC = {"utc", "etc/utc", "gmt", "etc/gmt", "z", "zulu", "universal", "etc/universal"}
_warned = set()


def zone(name):
    """tzinfo for an IANA name; None for an empty name or one that can't be loaded (the system's local zone)"""
    name = (name or "").strip()
    if not name:
        return None
    if name.lower() in _UTC:
        return datetime.timezone.utc
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception as e:   # ZoneInfoNotFoundError, ValueError (a malformed key), ImportError (Python < 3.9)
        if name not in _warned:
            _warned.add(name)
            print(f"CCM_TIMEZONE={name}: time zone not found ({type(e).__name__}) - using the system's local time zone. "
                  f"On Windows Python has no zone database of its own: python -m pip install tzdata", file=sys.stderr)
        return None
