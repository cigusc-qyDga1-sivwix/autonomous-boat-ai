from boat_ai.preview_api import parse_preview

def test_complete_preview_fixture():
    preview = {"racers": {str(i): {"course_number": i, "start_timing": .12, "exhibition_time": 6.8, "tilt_adjustment": 0} for i in range(1,7)}, "wind_speed": 3, "wave_height": 2}
    payload = {"programs": {"stadiums": {"20": {"races": {"6": {"preview": preview}}}}}}
    result = parse_preview(payload, 6)
    assert result["status"] == "complete"
    assert result["racers"]["3"]["start_timing"] == .12

def test_missing_preview():
    assert parse_preview({"programs": {"stadiums": {"20": {"races": {"6": {}}}}}}, 6)["status"] == "missing"

def test_incomplete_preview():
    payload = {"programs": {"stadiums": {"20": {"races": {"6": {"preview": {"racers": {"1": {"course_number": 1}}}}}}}}}}
    result = parse_preview(payload, 6)
    assert result["status"] == "incomplete"
    assert result["racers"]["1"]["exhibition_time"] is None
