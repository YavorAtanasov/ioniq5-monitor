import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sinks


def a_reading(soc=80.0):
    return {
        "measurement": "vehicle_status",
        "vehicle": "VIN",
        "tags": {},
        "fields": {"soc_pct": soc},
        "timestamp": "2026-01-01T10:00:00+00:00",
    }


def test_failed_write_is_spooled_and_replayed(tmp_path, monkeypatch):
    spool = tmp_path / "spool.jsonl"
    sink = sinks.CloudSink(url="https://cloud.example", api_key="k", spool_path=spool)
    monkeypatch.setattr(sink, "_post", _failing)

    with pytest.raises(RuntimeError):
        sink.write(a_reading(80.0))
    assert len(spool.read_text().strip().splitlines()) == 1

    posted = []
    monkeypatch.setattr(sink, "_post", posted.append)
    sink.write(a_reading(81.0))

    assert [r["fields"]["soc_pct"] for r in posted[0]] == [80.0, 81.0]
    assert not spool.exists()


def test_spool_is_capped(tmp_path, monkeypatch):
    spool = tmp_path / "spool.jsonl"
    sink = sinks.CloudSink(
        url="https://cloud.example", api_key="k", spool_path=spool, spool_max_lines=3
    )
    monkeypatch.setattr(sink, "_post", _failing)

    for soc in range(5):
        with pytest.raises(RuntimeError):
            sink.write(a_reading(float(soc)))

    spooled = [json.loads(line) for line in spool.read_text().strip().splitlines()]
    assert [r["fields"]["soc_pct"] for r in spooled] == [2.0, 3.0, 4.0]


def test_one_failing_sink_does_not_block_the_others(monkeypatch):
    written = []

    class Failing:
        name = "failing"

        def write(self, reading):
            raise RuntimeError("nope")

    class Working:
        name = "working"

        def write(self, reading):
            written.append(reading)

    monkeypatch.setattr(sinks, "_sinks", [Failing(), Working()])
    sinks.write_reading("vehicle_status", {"soc_pct": 80})

    assert len(written) == 1


def test_none_fields_are_dropped_and_numbers_coerced(monkeypatch):
    written = []

    class Capture:
        name = "capture"

        def write(self, reading):
            written.append(reading)

    monkeypatch.setattr(sinks, "_sinks", [Capture()])
    sinks.write_reading(
        "vehicle_status", {"soc_pct": 80, "range_km": None, "charging": True}
    )

    assert written[0]["fields"] == {"soc_pct": 80.0, "charging": True}


def test_build_sinks_requires_configuration(monkeypatch):
    for var in ("SINKS", "INFLUX_URL", "CLOUD_INGEST_URL", "CLOUD_AGENT_KEY"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(SystemExit):
        sinks.build_sinks()


def test_build_sinks_infers_from_environment(monkeypatch):
    monkeypatch.delenv("SINKS", raising=False)
    monkeypatch.setenv("INFLUX_URL", "http://influxdb:8086")
    monkeypatch.setenv("CLOUD_INGEST_URL", "https://cloud.example")
    monkeypatch.setenv("CLOUD_AGENT_KEY", "k")

    assert [s.name for s in sinks.build_sinks()] == ["influx", "cloud"]


def _failing(readings):
    raise RuntimeError("ingest unavailable")
