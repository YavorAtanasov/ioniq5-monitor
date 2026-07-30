import os
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

_client = None
_write_api = None


def _get_write_api():
    global _client, _write_api
    if _write_api is None:
        _client = InfluxDBClient(
            url=os.environ["INFLUX_URL"],
            token=os.environ["INFLUX_TOKEN"],
            org=os.environ["INFLUX_ORG"],
        )
        _write_api = _client.write_api(write_options=SYNCHRONOUS)
    return _write_api


def write_point(measurement, fields, tags=None, timestamp=None, vehicle_tag=None):
    tags = tags or {}
    timestamp = timestamp or datetime.now(timezone.utc)
    vehicle_tag = vehicle_tag or os.environ.get("BLUELINK_VIN", "default")

    point = Point(measurement).tag("vehicle", vehicle_tag)
    for k, v in tags.items():
        point = point.tag(k, str(v))
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, bool):
            point = point.field(k, v)
        elif isinstance(v, (int, float)):
            point = point.field(k, float(v))
        else:
            point = point.field(k, str(v))
    point = point.time(timestamp, WritePrecision.MS)

    write_api = _get_write_api()
    write_api.write(bucket=os.environ["INFLUX_BUCKET"], org=os.environ["INFLUX_ORG"], record=point)
