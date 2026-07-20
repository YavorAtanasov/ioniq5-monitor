# Ioniq 5 self-monitoring stack (hyundai_kia_connect_api + InfluxDB + Grafana)

## Why not bluelinky?
We switched away from bluelinky (Node.js) because its EU login has been broken on and off since August 2025 due to Hyundai/Kia rotating their EU auth backend faster than the library gets patched (see [issue #295](https://github.com/Hacksore/bluelinky/issues/295), [#307](https://github.com/Hacksore/bluelinky/issues/307), [#308](https://github.com/Hacksore/bluelinky/issues/308), all still open). We're now using **`hyundai_kia_connect_api`** (Python) instead — the library underneath Home Assistant's Kia Connect/Hyundai Bluelink integration, which has kept working through the same period (releases as recently as May 2026).

## Architecture
- **poller** (Python) — logs into Bluelink via `hyundai_kia_connect_api`, polls status + trip data on a schedule, writes to InfluxDB.
- **InfluxDB 2.x** — time-series storage.
- **Grafana** — pre-provisioned dashboard "Ioniq 5 Monitor".

## Running this on a Raspberry Pi 4
No changes needed to `docker-compose.yml` — `influxdb:2.7`, `grafana/grafana-oss:11.2.0`, and `python:3.12-slim` are all officially published for `arm64` as well as `amd64`, so Docker automatically pulls the right build for whatever machine it's running on. A few things specific to the Pi are worth knowing before you deploy, though:

1. **You need the 64-bit OS.** Run `uname -m` — it must print `aarch64`, not `armv7l`. If you're on 32-bit Raspberry Pi OS, InfluxDB 2.x has no maintained image for that architecture at all (only community forks, which we're not using here). If needed, reflash with **Raspberry Pi OS (64-bit)** via Raspberry Pi Imager, or Ubuntu Server 24.04 LTS (arm64).

2. **Install Docker + Compose:**
   ```bash
   curl -sSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   # log out and back in for the group change to take effect
   sudo apt install -y docker-compose-plugin
   ```

3. **RAM**: InfluxDB + Grafana + the poller together are comfortable on a 4GB or 8GB Pi 4. A 2GB model will likely struggle once Grafana is actively rendering dashboards — if that's what you have, consider it a soft requirement to upgrade, or at least keep an eye on `docker stats` under load.

4. **SD card wear**: InfluxDB writes fairly often (every status/trip poll). SD cards have limited write endurance and are also the most common failure point on long-running Pi projects. If this is going to run for months unattended, consider pointing the `influxdb-data` volume at a USB-attached SSD instead of the SD card — e.g. mount an SSD at `/mnt/ssd` and change the `influxdb-data` volume in `docker-compose.yml` to a bind mount there instead of a named Docker volume.

5. **Package installs**: the poller's `Dockerfile` now points pip at [piwheels](https://www.piwheels.org/), which hosts prebuilt ARM wheels for Python packages — without it, some dependencies would compile from source on the Pi's CPU, which is slow. This is harmless on non-ARM machines too (pip just won't find a match there and falls through to PyPI normally).

6. **Build and run, same as any other machine:**
   ```bash
   docker compose up -d --build
   ```

7. **If `influxdb`/`grafana` containers keep exiting with code 159**: that's signal 31 (`SIGSYS` — "bad system call"), meaning Docker's default seccomp filter is blocking a syscall one of these Go binaries makes that isn't in the default arm64 allow-list on this particular Raspberry Pi kernel. This isn't an outdated-Docker issue (confirmed on Docker 28.5.2 / kernel 6.12.48) - it's specific to Grafana/InfluxDB's syscall use on this kernel build. `docker-compose.yml` already sets `security_opt: seccomp:unconfined` on both services to work around it. This does loosen container syscall sandboxing slightly - reasonable for a home LAN project like this, worth knowing about if you're deploying somewhere more exposed.

## 1. First run: confirm the real field names
This library's `Vehicle` object fields aren't fully documented and can vary by brand/region/car generation. **Before trusting any numbers**, run the inspector once:

```bash
cd poller
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` at the **project root** (not inside `poller/`) — copy `.env.example` and fill in your real credentials, region (`EU`/`US`/`CA`), and brand (`hyundai`/`kia`/`genesis`).

```bash
python dump_fields.py
```

This dumps everything to `poller/data/raw-*.json`. Open `raw-vehicle_status.json` and `raw-day_trip_info.json` and compare the actual field names against the `g(vehicle, "...")` calls in `main.py`. If a field always comes back `None`, check the raw dump for the real name and adjust.

**One known gap:** per-trip energy consumption (kWh used/recuperated on a *single* trip) isn't reliably exposed by this library's trip API — only distance, average/max speed, drive time, and idle time per trip. Daily energy totals (`vehicle.daily_stats`) — consumed, regenerated, engine/climate/electronics/battery-care breakdown — cover the kWh side, but at daily rather than per-trip resolution. The inspector script tells you plainly if `daily_stats` isn't populating for your account (it may need a "force refresh" call rather than a cached one — check the raw dump).

## 2. Launch the stack
```bash
cd ..   # back to project root
docker compose up -d
```
- Grafana: http://localhost:3000 (admin / whatever you set in `.env`)
- InfluxDB UI: http://localhost:8086
- Dashboard "Ioniq 5 Monitor" is auto-provisioned under the **Ioniq 5** folder.

## 3. Polling frequency — be careful
Frequent live-status polling with a forced refresh can wake the car and drain the 12V battery. `poll_status()` uses `update_vehicle_with_cached_state` (cached only) and defaults to hourly. Trip polling defaults to every 30 minutes.

## What the dashboard shows (your requested metrics)
- Range (km), speed (avg/max per trip)
- Daily kWh consumed vs. kWh recuperated (per-trip granularity isn't available — see gap above)
- Daily kWh/100km efficiency
- State of charge over time, odometer trend

## Other signals this library exposes as extra widgets
- **Daily energy breakdown**: engine vs. climate vs. onboard electronics vs. battery-care conditioning.
- **12V battery %** — worth watching; frequent forced polling is a known cause of 12V drain on these cars.
- **Charging power (kW)** and plug/charging state.
- **Location** (lat/lon) — could feed a Grafana Geomap panel.
- **Doors/trunk/hood open state**, lock status, ignition state.
- **Climate**: AC on/off, defrost on/off.
- **Tire pressure warning** flag.
- **Idle minutes per trip** — a decent proxy for traffic/stop-start driving.
- **Lifetime cumulative energy consumed/regenerated** — some users have reported unit/scaling oddities in this counter for certain cars (see [this discussion](https://github.com/Hyundai-Kia-Connect/kia_uvo/discussions/817)); treat it as directional rather than exact until you've sanity-checked it against your own odometer/kWh math in `raw-vehicle_status.json`.

## Bug fix: daily energy (kWh consumed/regenerated) wasn't populating
Two issues, now fixed:
1. `DailyDrivingStats` uses a field called **`date`** (a Python `datetime` object) — my original code checked for a `yyyymmdd` string field that doesn't exist, so the match against each day silently failed every time and nothing ever got written.
2. Several users have reported `vehicle.daily_stats` only populates after a **forced** refresh (not the cached update status/trips use). Energy polling now runs on its own schedule (`ENERGY_POLL_MINUTES`, default every 4 hours) and explicitly forces a refresh first, since this is more API-costly than cached polls.

Check `docker compose logs -f poller` after this update — you should see lines like `[energy] daily_stats available for: [...]` and `[energy] 20260716: consumed=... regen=... kwh/100km=...`. If `daily_stats` still comes back empty after a forced refresh, that likely means this account/car doesn't expose it via the API at all (this has been reported for some models) — the log message will say so explicitly rather than failing silently.

## New: Car Location map
A Geomap panel plots `latitude`/`longitude` from `vehicle_status` (auto-centers on your data, shows up to the last 500 points). Only as fresh as your last status poll — with hourly cached polling this shows where the car was parked/last seen, not a live tracker.

## Dashboard fixes: stacked chart, series continuity, and a working map
- **Energy Used vs Recuperated per Day** is now a stacked bar chart.
- **Daily Energy Breakdown** and **Efficiency (kWh/100km) per Day** were splitting into a new color per day instead of one continuous series per metric. Cause: every `energy_daily` point carries a `date` tag in addition to its real timestamp, and Grafana treats each distinct tag value as its own series. Fixed by dropping that tag and regrouping by field in the query, so e.g. "engine_kwh" is now one line/bar across the whole time range instead of one per day.
- **Geomap** had two bugs: `basemap.type: "default"` isn't a valid Grafana basemap type (valid ones are `carto`, `osm-standard`, `esri-xyz`, `xyz`), and the marker layer's location config used the wrong key names (`latitudeField`/`longitudeField` instead of `latitude`/`longitude`). Both fixed.

## Fixed: geomap "blue box" and only-one-day-of-data
- **Geomap blue box**: with only 1-2 location points, the `fitData` auto-zoom computed a degenerate bounding box and zoomed in so far that a single marker filled the entire panel. Switched to a fixed initial view (rough Europe center, zoom 4) — pan/zoom manually for now; once more trip history builds up you can switch back to `fitData` if you want. Also switched the basemap to `carto` (Grafana's actual default).
- **Only one day of energy data**: `poll_energy_daily` was only ever checking a narrow date window tracked by its own state file, rather than everything the API actually returns. Other tools built on this library show the daily-stats endpoint can hand back more than one day per call. Fixed: it now writes out every day present in `vehicle.daily_stats` on each run, instead of only checking a self-tracked window. Writes are idempotent (same date = overwrite), so this is safe to repeat every 4 hours as more days become available.
- The stacked-bar-per-day view for consumed vs. regenerated kWh was already configured correctly (`stacking: normal` on both series) — once more days land in InfluxDB you should see exactly the "01/07 - 2kW regen, 5kW used / 02/07 - 5kW regen, 10kW used" comparison you described, one stacked bar per day.

## Fixed: poller logs showing up empty
`docker compose logs -f poller` could show nothing at all even while the poller was working fine in the background. Cause: Python fully buffers `print()` output when stdout isn't attached to a terminal (always true in Docker), so nothing reaches the log driver until the buffer fills up - which might never happen for a long-running loop like this one. Fixed by setting `PYTHONUNBUFFERED=1` and running `python -u main.py` in the Dockerfile, so every print flushes immediately.

## Fixed: timezone bug, trips table ordering, and real charge-time data
- **`energy_daily` timestamps showing the wrong day**: points were stamped at `23:00 UTC` on their tagged date, which crosses into the next calendar day for UTC+ timezones (e.g. Bulgaria: `23:00 UTC` on the 19th displays as `02:00` on the 20th in local time). Changed to `12:00 UTC` (noon), matching what `trips` already used - noon UTC stays on the same calendar day for any realistic timezone.
- **Recent Trips table showing older trips while newer ones existed**: the query had no explicit sort, so row order was arbitrary rather than newest-first. Added `sort(columns: ["_time"], desc: true)` plus a row limit.
- **Time to Full Charge showing 0**: this wasn't actually a bug - `ev_estimated_current_charge_duration` genuinely resets to 0 whenever the car isn't actively charging (confirmed against the library's own community discussions). Replaced it with the three fields that always have a value regardless of charging state: `ev_estimated_fast_charge_duration` (DC), `ev_estimated_station_charge_duration` (AC charging station), and `ev_estimated_portable_charge_duration` (mobile/ICCB charger) - now shown as three separate lines on "Time to Full Charge by Method".

## Ideas not yet wired up but easy to add
- **Cost tracking**: multiply `consumed_kwh` by your electricity tariff (a day/night split could turn this into a real cost dashboard given your off-peak strategy).
- **Efficiency vs. temperature**: pull local weather (e.g. Open-Meteo, no key needed) and correlate kWh/100km against outside temp.
- **Charge target vs. actual SoC**.
- **Alerting**: Grafana alert if 12V battery % drops below a threshold, or if SoC hasn't changed in N days (car sitting unused / dead 12V risk).

## Files
```
docker-compose.yml
.env.example
poller/
  Dockerfile
  requirements.txt
  common.py            # env loading, region/brand mapping, VehicleManager setup
  influx_writer.py      # InfluxDB write helper
  dump_fields.py             # run once - dumps raw vehicle/trip fields
  main.py                # scheduler: status + trip/energy polling
grafana/
  provisioning/
    datasources/datasource.yml
    dashboards/dashboards.yml
  dashboards/ioniq5-overview.json
```
