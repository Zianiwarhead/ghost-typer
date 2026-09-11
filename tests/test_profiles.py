from core.profiles import PROFILE_ORDER, clamp_wpm, get_profile, validate_profile


def test_new_presets_exist():
    for name in ["sluggish", "normal", "fast", "superfast", "typewriter", "insane"]:
        p = get_profile(name)
        assert 10 <= p["wpm"] <= 300


def test_preset_wpm_values():
    assert get_profile("sluggish")["wpm"] == 25
    assert get_profile("normal")["wpm"] == 65
    assert get_profile("fast")["wpm"] == 105
    assert get_profile("superfast")["wpm"] == 150
    assert get_profile("typewriter")["wpm"] == 80
    assert get_profile("insane")["wpm"] == 300


def test_typewriter_is_mechanical_no_burst():
    p = get_profile("typewriter")
    assert p["mechanical"] is True
    assert p["burst_chance"] == 0.0


def test_clamp_wpm():
    assert clamp_wpm(5) == 10
    assert clamp_wpm(500) == 300
    assert clamp_wpm(90) == 90


def test_case_insensitive_and_alias():
    assert get_profile("Normal")["wpm"] == 65
    assert get_profile("super-fast")["wpm"] == 150


def test_validate_fills_mechanical():
    p = validate_profile({"wpm": 70, "error_rate": 0.03})
    assert "mechanical" in p
    assert p["wpm"] == 70


def test_order_covers_all():
    from core.profiles import PROFILES
    assert set(PROFILE_ORDER) == set(PROFILES.keys())
