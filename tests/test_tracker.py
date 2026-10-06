from app.ai.detector import Detection
from app.ai.tracker import CentroidTracker, iou


def det(x, y, w=40, h=100):
    return Detection(x, y, x + w, y + h, 0.9)


def test_iou():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0
    assert round(iou([0, 0, 10, 10], [5, 0, 15, 10]), 3) == 0.333


def test_ids_persist_while_people_move():
    tracker = CentroidTracker()
    first = tracker.update([det(100, 100), det(400, 100)])
    ids = {t.track_id for t in first}
    for step in range(1, 10):
        tracks = tracker.update([det(100 + step * 5, 100), det(400 - step * 5, 100)])
        assert {t.track_id for t in tracks} == ids


def test_new_person_gets_new_id_and_lost_track_expires():
    tracker = CentroidTracker(max_missed=2)
    (a,) = tracker.update([det(100, 100)])
    tracks = tracker.update([det(100, 100), det(600, 300)])
    assert len({t.track_id for t in tracks}) == 2
    for _ in range(3):
        tracker.update([])
    (c,) = tracker.update([det(100, 100)])
    assert c.track_id != a.track_id
