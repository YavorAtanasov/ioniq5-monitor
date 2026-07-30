"""
Run this once before trusting main.py's field mapping:
    python dump_fields.py

hyundai_kia_connect_api's Vehicle dataclass fields (and whether daily energy
breakdown/trip lists populate) can vary by brand/region/car generation. This
dumps everything it can reach to data/raw-*.json so you can confirm the
field names main.py assumes actually exist for your account.
"""
import dataclasses
import json
from datetime import datetime
from pathlib import Path
import traceback

from common import get_vehicle_manager, get_target_vehicle

OUT_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR.mkdir(exist_ok=True)


def dump(name, data):
    path = OUT_DIR / f"raw-{name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Wrote {path}")


def to_dict(obj):
    if dataclasses.is_dataclass(obj):
        return dataclasses.asdict(obj)
    if hasattr(obj, "__dict__"):
        return {k: str(v) for k, v in vars(obj).items()}
    return str(obj)


def main():
    vm = get_vehicle_manager()
    print("Logging in...")
    vm.check_and_refresh_token()
    vm.update_all_vehicles_with_cached_state()

    vehicle = get_target_vehicle(vm)
    print(f"Connected to vehicle: {getattr(vehicle, 'name', vehicle.id)} (id={vehicle.id})")

    dump("vehicle_status", to_dict(vehicle))

    today = datetime.now()
    yyyymm = today.strftime("%Y%m")
    yyyymmdd = today.strftime("%Y%m%d")

    try:
        vm.update_month_trip_info(vehicle.id, yyyymm)
        dump("month_trip_info", to_dict(vehicle.month_trip_info))
    except Exception as e:  # broad catch to keep polling resilient; re-raises interrupts
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"⚠️  update_month_trip_info failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        dump("month_trip_info", {"error": str(e)})

    try:
        vm.update_day_trip_info(vehicle.id, yyyymmdd)
        dump("day_trip_info", to_dict(vehicle.day_trip_info))
    except Exception as e:  # broad catch to keep polling resilient; re-raises interrupts
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"⚠️  update_day_trip_info failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        dump("day_trip_info", {"error": str(e)})

    # Daily energy breakdown (engine/climate/electronics/battery-care/regen).
    # This lives on vehicle.daily_stats in most recent library versions, but
    # isn't guaranteed to populate on every brand/region without a force
    # refresh - hence dumping it explicitly here rather than assuming.
    daily_stats = getattr(vehicle, "daily_stats", None)
    if daily_stats:
        dump("daily_stats", [to_dict(d) for d in daily_stats])
    else:
        print("ℹ️  vehicle.daily_stats is empty/absent - daily energy breakdown may need a force refresh, "
              "or may not be exposed for this brand/region. Check raw-vehicle_status.json for alternatives.")

    print("\nDone. Open data/raw-*.json and compare field names against common.py / main.py before trusting the dashboards.")


if __name__ == "__main__":
    main()
