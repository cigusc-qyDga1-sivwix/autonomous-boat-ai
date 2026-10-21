from boat_ai.preview_api import parse_preview

def fixture(preview):
    return {"programs": {"stadiums": {"20": {"races": {"6": {"preview": preview}}}}}}

def test_complete_preview_fixture():
    preview = {
        "racers": {
            str(i): {
                "course_number": i, "start_timing": 0.12,
                "exhibition_time": 6.8, "tilt_adjustment": 0,
            }
            for i in range(1, 7)
        },
        "wind_speed": 3, "wave_height": 2,
    }
    result = parse_preview(fixture(preview), 6)
    assert result["status"] == "complete"
    assert result["racers"]["3"]["start_timing"] == 0.12

def test_missing_preview():
    result = parse_preview({"programs": {"stadiums": {"20": {"races": {"6": {}}}}}}, 6)
    assert result["status"] == "missing"

def test_incomplete_preview():
    result = parse_preview(fixture({"racers": {"1": {"course_number": 1}}}), 6)
    assert result["status"] == "incomplete"
    assert result["racers"]["1"]["exhibition_time"] is None
