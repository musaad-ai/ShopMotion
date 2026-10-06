from datetime import datetime, timedelta

from app.ai.behavior import BehaviorAnalyzer, ZoneRect
from app.ai.tracker import Track

ZONES = [ZoneRect(1, "Left", 0.0, 0.0, 0.5, 1.0), ZoneRect(2, "Right", 0.5, 0.0, 0.5, 1.0)]
T0 = datetime(2025, 1, 1, 12, 0, 0)


def person(track_id, foot_x, w=100, h=100):
    # Box whose bottom-centre (foot point) sits at (foot_x, h).
    return Track(track_id, foot_x - 5, h - 40, foot_x + 5, h)


def test_zone_lookup_uses_normalised_coordinates():
    analyzer = BehaviorAnalyzer(ZONES)
    assert analyzer.zone_for(0.2, 0.5) == 1
    assert analyzer.zone_for(0.8, 0.5) == 2


def test_visit_is_recorded_when_person_changes_zone():
    analyzer = BehaviorAnalyzer(ZONES)
    for s in range(10):
        analyzer.update([person("7", 20)], 100, 100, T0 + timedelta(seconds=s))
    analyzer.update([person("7", 80)], 100, 100, T0 + timedelta(seconds=10))
    visits, _, new_ids = analyzer.flush()
    assert new_ids == 1
    assert len(visits) == 1
    assert visits[0].zone_id == 1
    assert visits[0].dwell_seconds == 10


def test_lost_track_closes_visit_and_short_visits_are_ignored():
    analyzer = BehaviorAnalyzer(ZONES, lost_after=timedelta(seconds=2), min_dwell=1.0)
    analyzer.update([person("a", 20), person("b", 80)], 100, 100, T0)
    analyzer.update([person("a", 20)], 100, 100, T0 + timedelta(seconds=5))
    analyzer.update([], 100, 100, T0 + timedelta(seconds=10))
    visits, heat, _ = analyzer.flush()
    # "b" was only seen once (0 s dwell) so it is ignored; "a" stayed 5 s.
    assert [(v.track_id, v.dwell_seconds) for v in visits] == [("a", 5.0)]
    assert sum(heat.values()) == 3


def test_peak_and_total_counts():
    analyzer = BehaviorAnalyzer(ZONES)
    analyzer.update([person("1", 10), person("2", 60), person("3", 90)], 100, 100, T0)
    analyzer.update([person("1", 10)], 100, 100, T0 + timedelta(seconds=1))
    assert analyzer.peak_count == 3
    assert analyzer.total_detected == 3


def test_flush_close_all_ends_open_visits():
    analyzer = BehaviorAnalyzer(ZONES)
    analyzer.update([person("1", 10)], 100, 100, T0)
    analyzer.update([person("1", 10)], 100, 100, T0 + timedelta(seconds=30))
    visits, _, _ = analyzer.flush(T0 + timedelta(seconds=30), close_all=True)
    assert len(visits) == 1 and visits[0].dwell_seconds == 30
