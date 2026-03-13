"""
data_parser.py
==================================================================

PURPOSE
-------
Fetches per-pitch Statcast data from Baseball Savant (via pybaseball) and
computes pitcher/batter parameters for the PCSP# formal model.

INSTALL
-------
    pip install pybaseball pandas requests

HOW TO USE AS A MODULE
----------------------
    from data_parser import get_pitcher_stats, get_batter_stats, get_matchup, generate_pcsp_defines

    pitcher = get_pitcher_stats("Gerrit Cole")
    batter  = get_batter_stats("Aaron Judge")
    matchup = get_matchup("Gerrit Cole", "Aaron Judge")
    print(generate_pcsp_defines(matchup))

PARAMETER CONTRACT (must match baseball_template.pcsp #define names exactly)
-----------------------------------------------------------------------------
Pitch distribution (sum = 100):
    P_FAST_PCT, P_BREAK_PCT, P_OFF_PCT

Pitcher zone accuracy per pitch type (each pair sums to 100):
    P_FAST_ZONE,  P_FAST_MISS
    P_BREAK_ZONE, P_BREAK_MISS
    P_OFF_ZONE,   P_OFF_MISS

Batter swing rate per pitch type (each pair sums to 100):
    B_FAST_SWING,  B_FAST_TAKE
    B_BREAK_SWING, B_BREAK_TAKE
    B_OFF_SWING,   B_OFF_TAKE

Batter whiff/contact on a swing (each pair sums to 100):
    B_FAST_WHIFF,  B_FAST_CONTACT
    B_BREAK_WHIFF, B_BREAK_CONTACT
    B_OFF_WHIFF,   B_OFF_CONTACT

On-contact outcomes (each triple sums to 100):
    B_FAST_FOUL,  B_FAST_OUT,  B_FAST_HIT
    B_BREAK_FOUL, B_BREAK_OUT, B_BREAK_HIT
    B_OFF_FOUL,   B_OFF_OUT,   B_OFF_HIT

Win conditions in PAT model:
    result == 1  =>  pitcher wins  (strikeout or fielded out)
    result == 2  =>  batter wins   (base hit or walk)
"""

import io
import json
import requests
import pandas as pd
from pybaseball import statcast_pitcher, statcast_batter, playerid_lookup, cache

cache.enable()

# ── Season ────────────────────────────────────────────────────────────────────
SEASON     = 2024
START_DATE = f"{SEASON}-03-01"
END_DATE   = f"{SEASON}-11-01"

# ── Pitch type grouping ───────────────────────────────────────────────────────
# Fastball family: 4-seam, 2-seam/sinker, cutter
FAST_TYPES  = {"FF", "SI", "FT", "FA", "FC"}
# Breaking ball: slider, curveball, knuckle-curve, sweeper, slow curve
BREAK_TYPES = {"SL", "CU", "KC", "CS", "ST", "SV"}
# Offspeed: changeup, splitter, forkball, screwball
OFF_TYPES   = {"CH", "FS", "FO", "SC"}

# ── Statcast description categories ──────────────────────────────────────────
SWING_DESCS = {
    "swinging_strike", "swinging_strike_blocked",
    "foul", "foul_tip", "foul_bunt", "missed_bunt",
    "hit_into_play", "hit_into_play_no_out", "hit_into_play_score",
}
WHIFF_DESCS = {"swinging_strike", "swinging_strike_blocked"}

# Bat Tracking leaderboard pitch type codes per model group
# (fetched individually and weight-averaged by contact count)
BAT_TRACKING_CODES = {
    "fast":  ["FF", "SI", "FC", "FT"],
    "break": ["SL", "CU", "KC", "ST"],
    "off":   ["CH", "FS"],
}
BAT_TRACKING_URL = "https://baseballsavant.mlb.com/leaderboard/bat-tracking?csv=true&year={year}&pitchType={code}"

# ── Defaults (used when a pitch group has fewer than MIN_SAMPLES pitches) ─────
MIN_SAMPLES = 30

DEFAULTS = {
    "SWING": 65, "TAKE": 35,
    "WHIFF": 25, "CONTACT": 75,
    "FOUL": 38,  "OUT": 42,   "HIT": 20,
    "ZONE": 50,  "MISS": 50,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_mlbam_id(name: str) -> int:
    """Look up a player's MLB Advanced Media (Statcast) ID by full name."""
    parts = name.strip().rsplit(" ", 1)
    if len(parts) != 2:
        raise ValueError(f"Expected 'First Last' format, got: {name!r}")
    first, last = parts
    result = playerid_lookup(last, first)
    result = result.dropna(subset=["key_mlbam"])
    if result.empty:
        raise ValueError(f"Player not found in lookup table: {name!r}")
    # Pick the most recently active entry
    result = result.sort_values("mlb_played_last", ascending=False)
    return int(result.iloc[0]["key_mlbam"])


def _group_pitch(pt: str) -> str | None:
    if pd.isna(pt):
        return None
    if pt in FAST_TYPES:
        return "fast"
    if pt in BREAK_TYPES:
        return "break"
    if pt in OFF_TYPES:
        return "off"
    return None


def _pct(numerator: int, denominator: int, default: int) -> int:
    """Integer percentage, clamped to [1, 99]. Returns default if denominator is 0."""
    if denominator == 0:
        return default
    return max(1, min(99, round(100 * numerator / denominator)))


def _fix_triple(a: int, b: int, c: int) -> tuple[int, int, int]:
    """Adjust a, b, c so they sum to exactly 100 by tweaking a."""
    diff = 100 - a - b - c
    return max(1, a + diff), b, c


def _fix_pair(x: int) -> tuple[int, int]:
    """Return (x, 100-x) clamped so both are >= 1."""
    x = max(1, min(99, x))
    return x, 100 - x


def _get_squared_up(mlbam_id: int, group: str, season: int) -> float | None:
    """
    Fetch Squared-Up % Contact for a batter from the Bat Tracking leaderboard,
    weight-averaged across all pitch type codes in the group.

    Returns a float in [0, 1], or None if the player has no data for that group.
    """
    codes = BAT_TRACKING_CODES[group]
    total_contact = 0
    weighted_sum  = 0.0

    for code in codes:
        url = BAT_TRACKING_URL.format(year=season, code=code)
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            row = df[df["id"] == mlbam_id]
            if row.empty:
                continue
            n  = int(row["contact"].values[0])
            sq = float(row["squared_up_per_bat_contact"].values[0])
            weighted_sum  += sq * n
            total_contact += n
        except Exception:
            continue

    if total_contact == 0:
        return None
    return weighted_sum / total_contact


def _contact_from_squared_up(sq_up: float) -> tuple[int, int, int]:
    """
    Derive (foul, out, hit) integer percentages from Squared-Up % Contact.
    Formula from README Section 4.3:
        HIT  = Squared-Up %
        OUT  = (100 - HIT) * 0.7
        FOUL = 100 - HIT - OUT
    """
    hit  = max(1, min(98, round(sq_up * 100)))
    out  = max(1, round((100 - hit) * 0.7))
    foul = 100 - hit - out
    foul = max(1, foul)
    # Re-clamp in case rounding broke the sum
    foul, out, hit = _fix_triple(foul, out, hit)
    return foul, out, hit


# ── Public API ────────────────────────────────────────────────────────────────

def get_pitcher_stats(name: str, season: int = SEASON) -> dict:
    """
    Fetch pitcher parameters from Baseball Savant.

    Sources:
      - Pitch type distribution  →  P_FAST_PCT, P_BREAK_PCT, P_OFF_PCT
      - Zone% per pitch type     →  P_*_ZONE, P_*_MISS

    Returns a dict with all P_* keys (integer percentages).
    """
    player_id = _get_mlbam_id(name)
    print(f"[pitcher] Fetching Statcast data for {name} ({season})...")
    df = statcast_pitcher(f"{season}-03-01", f"{season}-11-01", player_id=player_id)

    if df.empty:
        raise ValueError(f"No Statcast data found for pitcher '{name}' in {season}.")

    df["group"] = df["pitch_type"].map(_group_pitch)
    df = df.dropna(subset=["group"])
    total = len(df)

    if total == 0:
        raise ValueError(f"No recognisable pitch types for '{name}' in {season}.")

    # ── Pitch distribution ────────────────────────────────────────────────────
    counts = df["group"].value_counts()
    fast_n  = int(counts.get("fast",  0))
    break_n = int(counts.get("break", 0))
    off_n   = int(counts.get("off",   0))

    p_fast  = _pct(fast_n,  total, 33)
    p_break = _pct(break_n, total, 33)
    p_off   = 100 - p_fast - p_break          # ensure sum = 100
    p_off   = max(1, p_off)
    # If rounding pushed p_off negative, rebalance
    if p_fast + p_break + p_off != 100:
        p_fast, p_break, p_off = _fix_triple(p_fast, p_break, p_off)

    # ── Zone accuracy ─────────────────────────────────────────────────────────
    stats = {
        "P_FAST_PCT":  p_fast,
        "P_BREAK_PCT": p_break,
        "P_OFF_PCT":   p_off,
    }

    for group, prefix in [("fast", "FAST"), ("break", "BREAK"), ("off", "OFF")]:
        g = df[df["group"] == group].dropna(subset=["zone"])
        if len(g) >= MIN_SAMPLES:
            in_zone = int(g["zone"].between(1, 9).sum())
            zone = _pct(in_zone, len(g), DEFAULTS["ZONE"])
        else:
            print(f"  [warn] {name}: only {len(g)} {group} pitches — using default zone%")
            zone = DEFAULTS["ZONE"]
        zone, miss = _fix_pair(zone)
        stats[f"P_{prefix}_ZONE"] = zone
        stats[f"P_{prefix}_MISS"] = miss

    print(f"  Pitch mix: fast={p_fast}% break={p_break}% off={p_off}%")
    return stats


def get_batter_stats(name: str, season: int = SEASON) -> dict:
    """
    Fetch batter parameters from Baseball Savant + Bat Tracking leaderboard.

    Sources:
      - Swing%  per pitch type  (Statcast pitch-by-pitch)  →  B_*_SWING, B_*_TAKE
      - Whiff%  per pitch type  (Statcast pitch-by-pitch)  →  B_*_WHIFF, B_*_CONTACT
      - Contact quality         (Bat Tracking leaderboard) →  B_*_FOUL, B_*_OUT, B_*_HIT
          HIT  = Squared-Up % Contact
          OUT  = (100 − HIT) × 0.7
          FOUL = 100 − HIT − OUT

    Returns a dict with all B_* keys (integer percentages).
    """
    player_id = _get_mlbam_id(name)
    print(f"[batter]  Fetching Statcast data for {name} ({season})...")
    df = statcast_batter(f"{season}-03-01", f"{season}-11-01", player_id=player_id)

    if df.empty:
        raise ValueError(f"No Statcast data found for batter '{name}' in {season}.")

    df["group"] = df["pitch_type"].map(_group_pitch)
    df = df.dropna(subset=["group"])

    print(f"[batter]  Fetching Bat Tracking leaderboard for {name} ({season})...")
    stats = {}

    for group, prefix in [("fast", "FAST"), ("break", "BREAK"), ("off", "OFF")]:
        g = df[df["group"] == group]

        if len(g) < MIN_SAMPLES:
            print(f"  [warn] {name}: only {len(g)} {group} pitches — using defaults")
            swing, take    = DEFAULTS["SWING"], DEFAULTS["TAKE"]
            whiff, contact = DEFAULTS["WHIFF"], DEFAULTS["CONTACT"]
            foul, out, hit = DEFAULTS["FOUL"],  DEFAULTS["OUT"],  DEFAULTS["HIT"]
        else:
            # ── Swing rate (Statcast) ─────────────────────────────────────────
            swings = g[g["description"].isin(SWING_DESCS)]
            swing, take = _fix_pair(_pct(len(swings), len(g), DEFAULTS["SWING"]))

            # ── Whiff rate on swings (Statcast) ───────────────────────────────
            whiffs = swings[swings["description"].isin(WHIFF_DESCS)]
            whiff, contact = _fix_pair(_pct(len(whiffs), len(swings), DEFAULTS["WHIFF"]))

            # ── Contact quality (Bat Tracking leaderboard — Squared-Up %) ────
            sq_up = _get_squared_up(player_id, group, season)
            if sq_up is not None:
                foul, out, hit = _contact_from_squared_up(sq_up)
            else:
                print(f"  [warn] {name}: no bat tracking data for {group} — using defaults")
                foul, out, hit = DEFAULTS["FOUL"], DEFAULTS["OUT"], DEFAULTS["HIT"]

        stats[f"B_{prefix}_SWING"]   = swing
        stats[f"B_{prefix}_TAKE"]    = take
        stats[f"B_{prefix}_WHIFF"]   = whiff
        stats[f"B_{prefix}_CONTACT"] = contact
        stats[f"B_{prefix}_FOUL"]    = foul
        stats[f"B_{prefix}_OUT"]     = out
        stats[f"B_{prefix}_HIT"]     = hit

    return stats


def get_matchup(pitcher_name: str, batter_name: str, season: int = SEASON) -> dict:
    """
    Returns combined dict with all P_* and B_* keys for a pitcher vs batter matchup.

    Example:
        matchup = get_matchup("Gerrit Cole", "Aaron Judge")
        print(generate_pcsp_defines(matchup))
    """
    pitcher_stats = get_pitcher_stats(pitcher_name, season)
    batter_stats  = get_batter_stats(batter_name, season)
    return {**pitcher_stats, **batter_stats}


def generate_pcsp_defines(matchup: dict) -> str:
    """
    Returns a PCSP# #define block string ready to prepend to baseball_template.pcsp.
    Paste this at the top of the template (replacing the existing #define block).
    """
    sections = [
        ("// Pitch type distribution (sum = 100)",
         ["P_FAST_PCT", "P_BREAK_PCT", "P_OFF_PCT"]),

        ("// Pitcher zone accuracy — in-zone vs ball (each pair sums to 100)",
         ["P_FAST_ZONE", "P_FAST_MISS",
          "P_BREAK_ZONE", "P_BREAK_MISS",
          "P_OFF_ZONE",   "P_OFF_MISS"]),

        ("// Batter swing rates per pitch type (each pair sums to 100)",
         ["B_FAST_SWING",  "B_FAST_TAKE",
          "B_BREAK_SWING", "B_BREAK_TAKE",
          "B_OFF_SWING",   "B_OFF_TAKE"]),

        ("// Batter whiff / contact on a swing (each pair sums to 100)",
         ["B_FAST_WHIFF",  "B_FAST_CONTACT",
          "B_BREAK_WHIFF", "B_BREAK_CONTACT",
          "B_OFF_WHIFF",   "B_OFF_CONTACT"]),

        ("// On-contact outcome — foul / fielded-out / base-hit (each triple sums to 100)",
         ["B_FAST_FOUL",  "B_FAST_OUT",  "B_FAST_HIT",
          "B_BREAK_FOUL", "B_BREAK_OUT", "B_BREAK_HIT",
          "B_OFF_FOUL",   "B_OFF_OUT",   "B_OFF_HIT"]),
    ]

    lines = ["// Auto-generated by data_parser.py — do not edit manually", ""]
    for comment, keys in sections:
        lines.append(comment)
        for key in keys:
            val = matchup.get(key, "???")
            lines.append(f"#define {key} {val};")
        lines.append("")

    return "\n".join(lines)


def export_matchup_json(pitcher_name: str, batter_name: str,
                        path: str = "data/matchup.json",
                        season: int = SEASON) -> dict:
    """
    Saves a matchup dict to JSON so other team members (Tresa, Sigrid) can load it
    without re-running the Statcast API calls.
    """
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    matchup = get_matchup(pitcher_name, batter_name, season)
    with open(path, "w") as f:
        json.dump(matchup, f, indent=2)
    print(f"\nSaved to {path}")
    return matchup


# ── CLI / smoke test ──────────────────────────────────────────────────────────
# Change the pitcher and batter names here to fetch different matchups, or run this file directly to see the output for Cole vs Judge.
if __name__ == "__main__":
    pitcher = "Gerrit Cole"
    batter  = "Aaron Judge"

    print(f"\n{'='*60}")
    print(f"  Matchup: {pitcher}  vs  {batter}  ({SEASON})")
    print(f"{'='*60}\n")

    matchup = get_matchup(pitcher, batter)

    print(f"\n{'─'*40}")
    print("  Raw parameter dict")
    print(f"{'─'*40}")
    for k, v in sorted(matchup.items()):
        print(f"  {k:<20} {v:>3}")

    print(f"\n{'─'*40}")
    print("  #define block for PAT")
    print(f"{'─'*40}")
    print(generate_pcsp_defines(matchup))

    # Save for teammates
    export_matchup_json(pitcher, batter)
