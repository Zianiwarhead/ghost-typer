"""
profiles.py — Built-in typing profiles and custom profile loader.
"""

import json
import os

# Built-in profiles — v2 speed ladder (WPM) + mechanical typewriter.
# Keys are stable; old keys kept for backward compatibility.
PROFILES = {
    "sluggish": {
        "name": "Sluggish",
        "description": "Slow hunt-and-peck style, ~25 WPM, heavy thinking pauses",
        "wpm": 25,
        "error_rate": 0.06,
        "transposition_rate": 0.005,
        "thinking_chance": 0.025,
        "burst_chance": 0.01,
        "fatigue_enabled": True,
        "errors_enabled": True,
        "mechanical": False,
    },
    "hunt_and_peck": {
        "name": "Hunt & Peck",
        "description": "Slow, one-finger style typist",
        "wpm": 20,
        "error_rate": 0.08,
        "transposition_rate": 0.005,
        "thinking_chance": 0.03,
        "burst_chance": 0.01,
        "fatigue_enabled": True,
        "errors_enabled": True,
        "mechanical": False,
    },
    "casual": {
        "name": "Casual Typist",
        "description": "Relaxed everyday typing, occasional mistakes",
        "wpm": 45,
        "error_rate": 0.05,
        "transposition_rate": 0.010,
        "thinking_chance": 0.018,
        "burst_chance": 0.04,
        "fatigue_enabled": True,
        "errors_enabled": True,
        "mechanical": False,
    },
    "normal": {
        "name": "Normal Human",
        "description": "Typical office worker, ~65 WPM (default)",
        "wpm": 65,
        "error_rate": 0.04,
        "transposition_rate": 0.008,
        "thinking_chance": 0.012,
        "burst_chance": 0.05,
        "fatigue_enabled": True,
        "errors_enabled": True,
        "mechanical": False,
    },
    "average": {
        "name": "Average Typist",
        "description": "Typical office worker, ~65 WPM (alias of Normal)",
        "wpm": 65,
        "error_rate": 0.04,
        "transposition_rate": 0.008,
        "thinking_chance": 0.012,
        "burst_chance": 0.05,
        "fatigue_enabled": True,
        "errors_enabled": True,
        "mechanical": False,
    },
    "typewriter": {
        "name": "Typewriter",
        "description": "Mechanical rhythm ~80 WPM, steady clack, carriage-return newline pause",
        "wpm": 80,
        "error_rate": 0.02,
        "transposition_rate": 0.005,
        "thinking_chance": 0.004,
        "burst_chance": 0.0,
        "fatigue_enabled": False,
        "errors_enabled": True,
        "mechanical": True,
    },
    "fast": {
        "name": "Fast Typist",
        "description": "Practiced typist, ~105 WPM, fewer errors",
        "wpm": 105,
        "error_rate": 0.025,
        "transposition_rate": 0.012,
        "thinking_chance": 0.007,
        "burst_chance": 0.08,
        "fatigue_enabled": True,
        "errors_enabled": True,
        "mechanical": False,
    },
    "expert": {
        "name": "Expert / Programmer",
        "description": "High-speed accurate typist, 120+ WPM",
        "wpm": 120,
        "error_rate": 0.015,
        "transposition_rate": 0.015,
        "thinking_chance": 0.004,
        "burst_chance": 0.12,
        "fatigue_enabled": False,
        "errors_enabled": True,
        "mechanical": False,
    },
    "superfast": {
        "name": "Super Fast",
        "description": "Near-bot ceiling ~150 WPM, still humanized",
        "wpm": 150,
        "error_rate": 0.015,
        "transposition_rate": 0.010,
        "thinking_chance": 0.003,
        "burst_chance": 0.12,
        "fatigue_enabled": False,
        "errors_enabled": True,
        "mechanical": False,
    },
    "flawless": {
        "name": "Flawless",
        "description": "No errors, variable speed only",
        "wpm": 70,
        "error_rate": 0.0,
        "transposition_rate": 0.0,
        "thinking_chance": 0.010,
        "burst_chance": 0.05,
        "fatigue_enabled": False,
        "errors_enabled": False,
        "mechanical": False,
    },
    "insane": {
        "name": "Insane",
        "description": "Ludicrous speed ~300 WPM, no errors, pauses, or fatigue",
        "wpm": 300,
        "error_rate": 0.0,
        "transposition_rate": 0.0,
        "thinking_chance": 0.0,
        "burst_chance": 0.0,
        "fatigue_enabled": False,
        "errors_enabled": False,
        "mechanical": False,
    },
}

# Canonical user-facing order for GUI / --list-profiles
PROFILE_ORDER = [
    "sluggish", "hunt_and_peck", "casual", "normal", "average",
    "typewriter", "fast", "expert", "superfast", "flawless", "insane",
]

WPM_MIN = 10
WPM_MAX = 300


def clamp_wpm(wpm: int) -> int:
    """Clamps WPM into the supported slider range."""
    return max(WPM_MIN, min(WPM_MAX, int(wpm)))


def validate_profile(profile: dict) -> dict:
    """Fills defaults, clamps WPM, normalizes flags. Returns the same dict."""
    defaults = dict(PROFILES["normal"])
    for key, value in defaults.items():
        profile.setdefault(key, value)
    profile["wpm"] = clamp_wpm(profile.get("wpm", 65))
    profile["mechanical"] = bool(profile.get("mechanical", False))
    profile["errors_enabled"] = bool(profile.get("errors_enabled", True))
    if not profile["errors_enabled"]:
        profile["error_rate"] = 0.0
        profile["transposition_rate"] = 0.0
    return profile


def get_profile(name: str) -> dict:
    """Returns a built-in profile by key name (case-insensitive)."""
    key = (name or "").strip().lower()
    # Friendly aliases
    aliases = {
        "normal-human": "normal",
        "super-fast": "superfast",
        "super_fast": "superfast",
        "hunt-and-peck": "hunt_and_peck",
    }
    key = aliases.get(key, key)
    if key not in PROFILES:
        available = ', '.join(PROFILE_ORDER)
        raise ValueError(f"Unknown profile '{name}'. Available: {available}")
    return validate_profile(dict(PROFILES[key]))


def load_custom_profile(path: str) -> dict:
    """Loads a user-defined profile from a JSON file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Profile file not found: {path}")

    with open(path, 'r') as f:
        data = json.load(f)

    # Validate required fields
    required = ['wpm', 'error_rate']
    for field in required:
        if field not in data:
            raise ValueError(f"Custom profile missing required field: '{field}'")

    # Fill in defaults for optional fields
    defaults = get_profile('normal')
    defaults.update(data)
    return validate_profile(defaults)


def save_custom_profile(profile: dict, path: str) -> None:
    """Saves a profile dict to a JSON file."""
    with open(path, 'w') as f:
        json.dump(profile, f, indent=2)
    print(f"Profile saved to {path}")


def list_profiles() -> None:
    """Prints all built-in profiles in a readable format."""
    print("\nAvailable Profiles:")
    print("-" * 60)
    for key in PROFILE_ORDER:
        p = PROFILES[key]
        mech = " [mechanical]" if p.get("mechanical") else ""
        print(f"  {key:<15} {p['wpm']:>4} WPM  —  {p['description']}{mech}")
    print(f"\n  Custom WPM range: {WPM_MIN}–{WPM_MAX} via --wpm N or GUI slider.\n")


def build_custom_profile_interactive() -> dict:
    """
    Interactive CLI wizard to build a custom profile.
    Returns the profile dict.
    """
    print("\n--- Custom Profile Builder ---")
    
    name = input("Profile name: ").strip() or "My Profile"
    
    wpm = int(input("Typing speed in WPM (e.g. 65): ").strip() or "65")
    
    errors = input("Enable typos? (y/n, default y): ").strip().lower()
    errors_enabled = errors != 'n'
    
    error_rate = 0.0
    transposition_rate = 0.0
    if errors_enabled:
        error_rate = float(input("Error rate 0.0–0.15 (default 0.04): ").strip() or "0.04")
        transposition_rate = float(input("Transposition rate 0.0–0.05 (default 0.008): ").strip() or "0.008")
    
    thinking = float(input("Thinking pause chance 0.0–0.05 (default 0.012): ").strip() or "0.012")
    fatigue = input("Enable fatigue slowdown? (y/n, default y): ").strip().lower()
    fatigue_enabled = fatigue != 'n'
    mech = input("Mechanical typewriter rhythm? (y/n, default n): ").strip().lower()
    mechanical = mech == 'y'

    profile = {
        "name": name,
        "description": "Custom profile",
        "wpm": wpm,
        "error_rate": error_rate,
        "transposition_rate": transposition_rate,
        "thinking_chance": thinking,
        "burst_chance": 0.0 if mechanical else 0.05,
        "fatigue_enabled": fatigue_enabled,
        "errors_enabled": errors_enabled,
        "mechanical": mechanical,
    }
    profile = validate_profile(profile)

    save = input("Save this profile to file? (y/n): ").strip().lower()
    if save == 'y':
        filename = input("Filename (e.g. myprofile.json): ").strip() or "custom_profile.json"
        save_custom_profile(profile, filename)

    return profile