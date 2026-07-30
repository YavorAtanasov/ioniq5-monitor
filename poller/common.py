import os
from pathlib import Path

from dotenv import load_dotenv
from hyundai_kia_connect_api import VehicleManager

# Always load the root .env regardless of the current working directory,
# since this file may be run directly (python main.py) or via Docker.
ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ROOT_ENV)

REGION_MAP = {
    "EU": 1,
    "CA": 2,
    "US": 3,
    "CHINA": 4,
    "AU": 5,
    "IN": 6,
    "NZ": 7,
    "BR": 8,
}

BRAND_MAP = {
    "KIA": 1,
    "HYUNDAI": 2,
    "GENESIS": 3,
}


def require_env():
    missing = [
        k
        for k in ("BLUELINK_USERNAME", "BLUELINK_PASSWORD", "BLUELINK_REGION", "BLUELINK_BRAND")
        if not os.environ.get(k)
    ]
    if missing:
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Expected a filled-in .env file at: {ROOT_ENV}"
        )


def get_vehicle_manager() -> VehicleManager:
    require_env()
    region = REGION_MAP.get(os.environ["BLUELINK_REGION"].upper())
    brand = BRAND_MAP.get(os.environ["BLUELINK_BRAND"].upper())
    if region is None or brand is None:
        raise SystemExit(
            f"Unrecognized BLUELINK_REGION/BLUELINK_BRAND. "
            f"Region must be one of {list(REGION_MAP)}, brand one of {list(BRAND_MAP)}."
        )

    vm = VehicleManager(
        region=region,
        brand=brand,
        username=os.environ["BLUELINK_USERNAME"],
        password=os.environ["BLUELINK_PASSWORD"],
        pin=os.environ.get("BLUELINK_PIN", ""),
        language=os.environ.get("BLUELINK_LANGUAGE", "en"),
    )
    return vm


def get_target_vehicle(vm: VehicleManager):
    vin = os.environ.get("BLUELINK_VIN")
    if vin:
        for v in vm.vehicles.values():
            if v.VIN == vin or getattr(v, "vin", None) == vin:
                return v
    # fall back to the first vehicle on the account
    vehicles = list(vm.vehicles.values())
    if not vehicles:
        raise SystemExit("No vehicles found on this account.")
    return vehicles[0]
