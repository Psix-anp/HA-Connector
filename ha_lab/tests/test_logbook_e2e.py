"""End-to-end Meshtastic Logbook tests against a real HA container."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote


def _find_entities(ha):
    states = ha.api("GET", "states").json()
    by_name = {
        item.get("attributes", {}).get("friendly_name"): item["entity_id"]
        for item in states
        if item["entity_id"].startswith("meshtastic.")
    }
    assert "Direct Messages" in by_name, by_name
    assert "Channel Primary" in by_name, by_name
    return by_name["Direct Messages"], by_name["Channel Primary"]


def _wait_for_logbook_marker(ha, entity_id: str, marker: str, timeout: float = 20.0):
    start = datetime.now(timezone.utc) - timedelta(minutes=2)
    end = datetime.now(timezone.utc) + timedelta(minutes=2)
    path = (
        f"logbook/{quote(start.isoformat(), safe='')}"
        f"?end_time={quote(end.isoformat(), safe='')}&entity={quote(entity_id, safe='')}"
    )
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        response = ha.api("GET", path)
        assert response.status_code == 200, response.text
        latest = response.json()
        for row in latest:
            if marker in str(row.get("message", "")):
                assert row.get("entity_id") == entity_id, row
                assert row.get("domain") == "meshtastic", row
                return row
        time.sleep(1)
    raise AssertionError(
        f"Marker {marker!r} never appeared in Activity for {entity_id}; last rows={latest!r}"
    )


def test_direct_message_and_channel_reach_real_logbook(ha):
    """A real HA Recorder/Logbook query must return both message types."""
    dm_entity, channel_entity = _find_entities(ha)

    for target, entity_id in (("dm", dm_entity), ("channel", channel_entity)):
        marker = f"HA-LAB-{target.upper()}-{uuid.uuid4().hex[:10]}"
        response = ha.api(
            "POST",
            "services/meshtastic_lab/inject_message",
            json={"target": target, "message": marker},
        )
        assert response.status_code == 200, response.text
        row = _wait_for_logbook_marker(ha, entity_id, marker)
        assert marker in row["message"]

    error_log = ha.api("GET", "error_log")
    assert error_log.status_code == 200
    text = error_log.text
    forbidden = (
        "Error while processing event meshtastic_api_text_message",
        "NameError: name 'Mapping' is not defined",
        "Error with meshtastic describe event",
    )
    assert not any(item in text for item in forbidden), text
