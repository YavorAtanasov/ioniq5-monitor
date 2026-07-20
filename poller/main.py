import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import schedule

from common import get_vehicle_manager, get_target_vehicle
from influx_writer import write_point

STATE_FILE = Path(__file__).resolve().parent / "data" / "state.json"
STATE_FILE.parent.mkdir(exist_ok=True)


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"last_trip_date": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def g(obj, name, default=None):
    """getattr with a default, since not every field exists on every brand/region."""
    return getattr(obj, name, default)


# ---------------- STATUS POLL ----------------
def poll_status(vm, vehicle):
    vm.check_and_refresh_token()
    vm.update_vehicle_with_cached_state(vehicle.id)  # cached only - doesn't wake the car

    fields = {
        "soc_pct": g(vehicle, "ev_battery_percentage"),
        "range_km": g(vehicle, "ev_driving_range", g(vehicle, "total_driving_range")),
        "odometer_km": g(vehicle, "odometer"),
        "battery12v_pct": g(vehicle, "car_battery_percentage"),
        "is_charging": g(vehicle, "ev_battery_is_charging"),
        "is_plugged_in": g(vehicle, "ev_battery_is_plugged_in"),
        "charging_power_kw": g(vehicle, "ev_charging_power"),
        "charge_time_dc_min": g(vehicle, "ev_estimated_fast_charge_duration"),
        "charge_time_station_min": g(vehicle, "ev_estimated_station_charge_duration"),
        "charge_time_mobile_min": g(vehicle, "ev_estimated_portable_charge_duration"),
        "ac_on": g(vehicle, "air_control_is_on"),
        "defrost_on": g(vehicle, "defrost_is_on"),
        "door_locked": g(vehicle, "is_locked"),
        "trunk_open": g(vehicle, "trunk_is_open"),
        "hood_open": g(vehicle, "hood_is_open"),
        "door_fl_open": g(vehicle, "front_left_door_is_open"),
        "door_fr_open": g(vehicle, "front_right_door_is_open"),
        "door_bl_open": g(vehicle, "back_left_door_is_open"),
        "door_br_open": g(vehicle, "back_right_door_is_open"),
        "ignition_on": g(vehicle, "engine_is_running"),
        "tire_warning": g(vehicle, "tire_pressure_all_warning_is_on"),
        "latitude": g(vehicle, "location_latitude"),
        "longitude": g(vehicle, "location_longitude"),
        # lifetime cumulative counters, if exposed for this brand/region
        "lifetime_energy_consumed_kwh": _wh_to_kwh(g(vehicle, "total_energy_consumption")),
        "lifetime_energy_regen_kwh": _wh_to_kwh(g(vehicle, "total_energy_regeneration")),
    }

    write_point("vehicle_status", fields)
    print(f"[status] soc={fields['soc_pct']} range={fields['range_km']} odo={fields['odometer_km']}")


def _wh_to_kwh(value):
    if value is None:
        return None
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return None


# ---------------- TRIPS POLL (distance/speed/time - cached, safe to poll often) ----------------
def poll_trips(vm, vehicle, state):
    today = datetime.now()
    if state.get("last_trip_date"):
        start = datetime.fromisoformat(state["last_trip_date"])
    else:
        start = today - timedelta(days=6)  # first run: backfill a week

    date = start
    while date.date() <= today.date():
        yyyymmdd = date.strftime("%Y%m%d")
        try:
            vm.update_day_trip_info(vehicle.id, yyyymmdd)
            day_info = g(vehicle, "day_trip_info")
            trip_list = g(day_info, "trip_list", []) if day_info else []
            day_ts = datetime.strptime(yyyymmdd, "%Y%m%d").replace(hour=12, tzinfo=timezone.utc)
            for idx, trip in enumerate(trip_list):
                fields = {
                    "distance_km": g(trip, "distance"),
                    "duration_min": g(trip, "drive_time"),
                    "idle_min": g(trip, "idle_time"),
                    "avg_speed_kmh": g(trip, "avg_speed"),
                    "max_speed_kmh": g(trip, "max_speed"),
                    # NOTE: per-trip energy (kWh consumed/regenerated) is not
                    # reliably exposed by this library's TripInfo - only
                    # distance/speed/time. poll_energy_daily() below covers energy.
                }
                write_point("trips", fields, tags={"date": yyyymmdd, "trip_index": idx}, timestamp=day_ts)
            # Always log, even when empty - a silent "nothing to write" here
            # was previously indistinguishable from a broken query.
            print(f"[trips] {yyyymmdd}: day_info={'present' if day_info else 'MISSING'}, "
                  f"trip_list has {len(trip_list)} entr{'y' if len(trip_list) == 1 else 'ies'}")
        except Exception as e:
            print(f"[trips] {yyyymmdd} FAILED: {type(e).__name__}: {e}")

        date += timedelta(days=1)

    state["last_trip_date"] = today.isoformat()
    save_state(state)


# ---------------- DAILY ENERGY POLL (needs a forced refresh, less frequent) ----------------
def _stat_date_str(stat):
    """DailyDrivingStats.date is a datetime/date object, not a yyyymmdd string - convert it."""
    dt = g(stat, "date")
    if dt is None:
        return None
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y%m%d")
    return str(dt)


def poll_energy_daily(vm, vehicle, state):
    # Daily energy breakdown (vehicle.daily_stats) has been reported to only
    # populate after a forced refresh, not a cached update - so this runs on
    # its own slower schedule and explicitly forces a refresh first.
    try:
        if hasattr(vm, "force_refresh_vehicles_states"):
            vm.force_refresh_vehicles_states(vehicle.id)
        elif hasattr(vm, "force_refresh_vehicle_state"):
            vm.force_refresh_vehicle_state(vehicle.id)
        else:
            vm.force_refresh_all_vehicles_states()
    except Exception as e:
        print(f"force refresh for daily energy failed, continuing with cached data: {e}")

    daily_stats = g(vehicle, "daily_stats", []) or []
    available_dates = [_stat_date_str(d) for d in daily_stats]
    if not daily_stats:
        print("[energy] vehicle.daily_stats is empty after force refresh - "
              "this brand/region/account may not expose it, or needs update_month_trip_info first.")
        return
    else:
        print(f"[energy] daily_stats available for: {available_dates}")

    # Write out EVERY day the API gives us, rather than only checking a
    # narrow window tracked by our own state file. The API can return more
    # history than a day at a time, and our old date-walking logic was
    # silently missing it. Writes are idempotent (same date = overwrite),
    # so this is safe to repeat every run.
    for match in daily_stats:
        yyyymmdd = _stat_date_str(match)
        if not yyyymmdd:
            continue
        distance = g(match, "distance")
        consumed_kwh = _wh_to_kwh(g(match, "total_consumed"))
        regen_kwh = _wh_to_kwh(g(match, "regenerated_energy"))
        kwh_per_100km = (
            (consumed_kwh / distance) * 100 if consumed_kwh is not None and distance else None
        )
        day_ts = datetime.strptime(yyyymmdd, "%Y%m%d").replace(hour=12, tzinfo=timezone.utc)
        write_point(
            "energy_daily",
            {
                "distance_km": distance,
                "consumed_kwh": consumed_kwh,
                "regen_kwh": regen_kwh,
                "kwh_per_100km": kwh_per_100km,
                "engine_kwh": _wh_to_kwh(g(match, "engine_consumption")),
                "climate_kwh": _wh_to_kwh(g(match, "climate_consumption")),
                "devices_kwh": _wh_to_kwh(g(match, "onboard_electronics_consumption")),
                "battery_care_kwh": _wh_to_kwh(g(match, "battery_care_consumption")),
            },
            tags={"date": yyyymmdd},
            timestamp=day_ts,
        )
        print(f"[energy] {yyyymmdd}: consumed={consumed_kwh} regen={regen_kwh} kwh/100km={kwh_per_100km}")


# ---------------- SCHEDULER ----------------
def main():
    print("Starting up...", flush=True)
    state = load_state()
    print("Loaded local state, connecting to Bluelink/Kia Connect...", flush=True)
    vm = get_vehicle_manager()
    print("VehicleManager created, logging in (this can take a few seconds)...", flush=True)
    vm.check_and_refresh_token()
    print("Logged in, fetching vehicle list...", flush=True)
    vm.update_all_vehicles_with_cached_state()
    vehicle = get_target_vehicle(vm)
    print(f"Poller ready for vehicle id={vehicle.id}", flush=True)

    status_minutes = int(os.environ.get("STATUS_POLL_MINUTES", "60"))
    trip_minutes = int(os.environ.get("TRIP_POLL_MINUTES", "30"))
    energy_minutes = int(os.environ.get("ENERGY_POLL_MINUTES", "240"))  # forces a refresh - keep infrequent

    def run_status():
        try:
            poll_status(vm, vehicle)
        except Exception as e:
            print(f"poll_status error: {e}")

    def run_trips():
        try:
            poll_trips(vm, vehicle, state)
        except Exception as e:
            print(f"poll_trips error: {e}")

    def run_energy():
        try:
            poll_energy_daily(vm, vehicle, state)
        except Exception as e:
            print(f"poll_energy_daily error: {e}")

    run_status()
    run_trips()
    run_energy()

    schedule.every(status_minutes).minutes.do(run_status)
    schedule.every(trip_minutes).minutes.do(run_trips)
    schedule.every(energy_minutes).minutes.do(run_energy)

    print(f"Scheduled: status every {status_minutes}m, trips every {trip_minutes}m, energy (forced) every {energy_minutes}m")
    while True:
        schedule.run_pending()
        time.sleep(5)


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except SystemExit as e:
        print(f"Exiting: {e}", flush=True)
        sys.exit(1)
    except Exception:
        print("FATAL - unhandled exception:", flush=True)
        traceback.print_exc()
        sys.exit(1)
