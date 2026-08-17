"""Where polled readings go.

The poller historically wrote straight to a local InfluxDB. For the hosted
product the same agent runs on the owner's hardware - so their Bluelink
credentials never leave it - and forwards readings to the cloud API instead of
(or as well as) Influx.
"""

import json
import os
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SPOOL_PATH = Path(__file__).resolve().parent / "data" / "spool.jsonl"
# Roughly a week of readings at the default poll intervals; old entries are
# dropped first so a long outage can't fill up an SD card.
DEFAULT_SPOOL_MAX_LINES = 20000


def _coerce_fields(fields):
    out = {}
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = float(v)
        else:
            out[k] = str(v)
    return out


class InfluxSink:
    """Writes to a local InfluxDB - the self-hosted setup."""

    name = "influx"

    def __init__(self):
        self._write_api = None
        self._client = None

    def _api(self):
        if self._write_api is None:
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import SYNCHRONOUS

            self._client = InfluxDBClient(
                url=os.environ["INFLUX_URL"],
                token=os.environ["INFLUX_TOKEN"],
                org=os.environ["INFLUX_ORG"],
            )
            self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        return self._write_api

    def write(self, reading):
        from influxdb_client import Point, WritePrecision

        point = Point(reading["measurement"]).tag("vehicle", reading["vehicle"])
        for k, v in reading["tags"].items():
            point = point.tag(k, str(v))
        for k, v in reading["fields"].items():
            point = point.field(k, v)
        point = point.time(
            datetime.fromisoformat(reading["timestamp"]), WritePrecision.MS
        )
        self._api().write(
            bucket=os.environ["INFLUX_BUCKET"],
            org=os.environ["INFLUX_ORG"],
            record=point,
        )


class CloudSink:
    """Forwards readings to the hosted ingest API.

    Only readings travel over the wire - the agent authenticates with a device
    API key issued during enrollment, so account credentials stay on this
    machine. Readings are spooled to disk when the API is unreachable (home
    internet outages are routine) and replayed on the next successful write.
    """

    name = "cloud"

    def __init__(self, url=None, api_key=None, spool_path=None, spool_max_lines=None):
        self.url = (url or os.environ.get("CLOUD_INGEST_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("CLOUD_AGENT_KEY", "")
        self.spool_path = Path(
            spool_path or os.environ.get("CLOUD_SPOOL_PATH") or DEFAULT_SPOOL_PATH
        )
        self.spool_max_lines = int(
            spool_max_lines
            or os.environ.get("CLOUD_SPOOL_MAX_LINES")
            or DEFAULT_SPOOL_MAX_LINES
        )
        self._lock = threading.Lock()

    def write(self, reading):
        with self._lock:
            batch = self._drain_spool() + [reading]
            try:
                self._post(batch)
            except Exception as e:
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                self._spool(batch)
                raise

    def _post(self, readings):
        import requests

        response = requests.post(
            f"{self.url}/v1/ingest",
            json={"readings": readings},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        response.raise_for_status()

    def _drain_spool(self):
        if not self.spool_path.exists():
            return []
        lines = self.spool_path.read_text().splitlines()
        self.spool_path.unlink()
        readings = []
        for line in lines:
            try:
                readings.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return readings

    def _spool(self, readings):
        self.spool_path.parent.mkdir(parents=True, exist_ok=True)
        existing = (
            self.spool_path.read_text().splitlines() if self.spool_path.exists() else []
        )
        lines = existing + [json.dumps(r) for r in readings]
        self.spool_path.write_text("\n".join(lines[-self.spool_max_lines :]) + "\n")


def build_sinks():
    """Pick sinks from the environment.

    `SINKS=influx,cloud` is explicit; otherwise a sink is enabled when its
    configuration is present, which keeps existing self-hosted `.env` files
    working untouched.
    """
    configured = os.environ.get("SINKS")
    if configured:
        names = [n.strip() for n in configured.split(",") if n.strip()]
    else:
        names = []
        if os.environ.get("INFLUX_URL"):
            names.append("influx")
        if os.environ.get("CLOUD_INGEST_URL") and os.environ.get("CLOUD_AGENT_KEY"):
            names.append("cloud")

    sinks = []
    for name in names:
        if name == "influx":
            sinks.append(InfluxSink())
        elif name == "cloud":
            sinks.append(CloudSink())
        else:
            raise SystemExit(
                f"Unknown sink '{name}' in SINKS. Known sinks: influx, cloud."
            )
    if not sinks:
        raise SystemExit(
            "No sink configured. Set INFLUX_URL for a local InfluxDB, or "
            "CLOUD_INGEST_URL + CLOUD_AGENT_KEY to forward to the hosted API."
        )
    return sinks


_sinks = None


def get_sinks():
    global _sinks
    if _sinks is None:
        _sinks = build_sinks()
    return _sinks


def write_reading(measurement, fields, tags=None, timestamp=None, vehicle_tag=None):
    """Fan a reading out to every configured sink.

    One failing sink must not stop the others, and no sink failure may kill the
    poll loop - a cloud outage should never cost the owner local data.
    """
    reading = {
        "measurement": measurement,
        "vehicle": vehicle_tag or os.environ.get("BLUELINK_VIN", "default"),
        "tags": {k: str(v) for k, v in (tags or {}).items()},
        "fields": _coerce_fields(fields),
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
    }

    for sink in get_sinks():
        try:
            sink.write(reading)
        except Exception as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            print(f"[{sink.name}] write failed: {type(e).__name__}: {e}")
            traceback.print_exc()
