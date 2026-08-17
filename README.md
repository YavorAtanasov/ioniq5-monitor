# Ioniq 5 Monitor

Self-hosted dashboard for your Hyundai/Kia electric vehicle — state of charge, range, efficiency, daily energy breakdown, trip history, location, and more — running entirely on your own hardware with no cloud service or subscription involved.

It works by polling the same unofficial cloud API that the Bluelink / Kia Connect mobile apps use, storing the data in a local time-series database, and visualizing it with Grafana.

![stack](https://img.shields.io/badge/stack-Python%20%2B%20InfluxDB%20%2B%20Grafana-blue)

> **Disclaimer**: This project is not affiliated with, endorsed by, or supported by Hyundai, Kia, or Genesis. It uses an unofficial, reverse-engineered API via the [`hyundai_kia_connect_api`](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api) library (the same one behind the popular Home Assistant integration). That API can change or break at any time without notice, and using it is entirely at your own risk.

## What you get

A pre-built Grafana dashboard with:

- **State of charge & range** over time
- **Efficiency**: daily kWh/100km, plus a rolling 30-day trend gauge
- **Daily energy breakdown**: how much of your consumption was driving vs. climate vs. onboard electronics vs. battery conditioning — both in kWh and as a percentage
- **Trips**: distance, average/max speed, idle-time ratio per day
- **Charging**: charging power, time-to-full by method (AC / DC / mobile), your configured charge limits and the range they translate to
- **Schedule**: off-peak charging window and departure/preconditioning schedule, at a glance
- **Vehicle state**: doors/trunk/hood, lock state, ignition, climate control, tire pressure warnings, 12V battery health
- **Location**: last known position on a map

All of it lives in your own InfluxDB instance, so it's yours to keep, query, or export — no third party ever sees it.

## How it works

```
Bluelink / Kia Connect account
        │  (unofficial API, via hyundai_kia_connect_api)
        ▼
   poller (Python)  ──writes──▶  InfluxDB 2.x  ──queries──▶  Grafana dashboard
```

- **poller** — a small Python service that logs into your account and polls vehicle status, trip history, and daily energy stats on a schedule.
- **InfluxDB** — stores everything as time-series data.
- **Grafana** — a pre-provisioned dashboard, ready as soon as the stack starts.

The poller can write to more than one destination. Alongside a local InfluxDB it
can forward readings to a hosted API (see [`cloud/`](cloud/README.md)) so a
dashboard is reachable from anywhere - while your Bluelink credentials never
leave your own hardware. Neither is required: leave `CLOUD_INGEST_URL` unset and
nothing changes.

Everything runs in Docker, on your own machine (a Raspberry Pi, a home server, a NAS, whatever you've got).

## Before you start: a note on API rate limits

Hyundai and Kia don't publish an official rate limit, but their backend **will** temporarily lock you out (usually with an error like *"maximum number of daily vehicle checks exceeded"*) if too many requests come from your account in a day — including from the official app itself. Community-sourced numbers ([bluelinky wiki](https://github.com/Hacksore/bluelinky/wiki/API-Rate-Limits)) suggest roughly:

| Region | Approx. daily limit |
|--------|---------------------|
| EU     | ~200 requests |
| USA    | ~30 requests (≈10 per action type) |
| CA     | not well documented; ~90s minimum between vehicle commands |

These aren't official, aren't guaranteed to stay accurate, and can vary by account. A few important, related facts:

- **Cached vs. forced requests are not equal.** A *cached* status check just reads the last data Hyundai/Kia's servers already have — cheap, and doesn't touch the car. A *forced refresh* wakes the car up over the mobile network to get fresh data — much more expensive, and the main known cause of unnecessary 12V battery drain on these cars.
- **This project defaults to being conservative** to stay well under any limit while running 24/7:
  - Status polling: every 60 minutes, **cached only**.
  - Trip polling: every 30 minutes, **cached only**.
  - Daily energy breakdown: every 4 hours, and this one *does* force a refresh (it's the only data that requires it) — kept infrequent deliberately.
- **Other apps count against the same limit.** If you also use the official Bluelink/Kia Connect app, a third-party integration (Home Assistant, Optiwatt, etc.), or run this monitor from more than one place at once, they all share the same per-account daily allowance.
- If you get locked out, it typically clears after 24 hours. If it keeps happening, increase `STATUS_POLL_MINUTES` / `TRIP_POLL_MINUTES` / `ENERGY_POLL_MINUTES` in your `.env` before doing anything else.

**In short: the defaults are already tuned to be safe for continuous use. If you make polling more frequent, you're trading dashboard freshness for a real risk of getting rate-limited or draining your 12V battery.**

## Requirements

- Docker + Docker Compose
- A Hyundai Bluelink, Kia Connect, or Genesis Connect account with a vehicle already registered
- ~2GB RAM free for the stack (see the Raspberry Pi notes below if you're tight on resources)

## Quick start

1. **Clone the repo and set up your credentials:**
   ```bash
   git clone https://github.com/YavorAtanasov/ioniq5-monitor.git
   cd ioniq5-monitor
   cp .env.example .env
   ```
   Edit `.env` with your Bluelink/Kia Connect username, password, PIN, region (`EU`/`US`/`CA`), and brand (`hyundai`/`kia`/`genesis`).

2. **(Recommended) Confirm your account's real field names first.** The underlying API varies subtly by brand, region, and car generation, so it's worth a one-time check before trusting any numbers:
   ```bash
   cd poller
   python3 -m venv venv
   source venv/bin/activate        # on Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python dump_fields.py
   cd ..
   ```
   This writes everything your account actually returns to `poller/data/raw-*.json`, so you can sanity-check it if a panel ever looks wrong.

3. **Launch the stack:**
   ```bash
   docker compose up -d
   ```

4. **Open the dashboard:**
   - Grafana: [http://localhost:3000](http://localhost:3000) (login with `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` from your `.env`) — the "Ioniq 5 Monitor" dashboard is auto-provisioned and ready immediately.
   - InfluxDB UI: [http://localhost:8086](http://localhost:8086), if you want to query the raw data directly.

It can take a few polling cycles (up to an hour, by default) before the dashboard has enough data to look interesting — the first few charts will fill in as the poller runs.

## Configuration reference (`.env`)

| Variable | What it does |
|---|---|
| `BLUELINK_USERNAME` / `BLUELINK_PASSWORD` / `BLUELINK_PIN` | Your Bluelink/Kia Connect/Genesis Connect account credentials |
| `BLUELINK_BRAND` | `hyundai`, `kia`, or `genesis` |
| `BLUELINK_REGION` | `EU`, `US`, or `CA` |
| `BLUELINK_VIN` | (Optional) pick a specific vehicle if your account has more than one |
| `STATUS_POLL_MINUTES` | How often to check live status (cached, default 60) |
| `TRIP_POLL_MINUTES` | How often to check for new trips (cached, default 30) |
| `ENERGY_POLL_MINUTES` | How often to pull the daily energy breakdown (forces a refresh, default 240 — see the rate-limit note above) |
| `INFLUX_*` / `GRAFANA_*` | Storage/dashboard credentials — the defaults in `.env.example` work out of the box for local/home use, but change the passwords if this will be reachable from outside your LAN |
| `CLOUD_INGEST_URL` / `CLOUD_AGENT_KEY` | (Optional) forward readings to a hosted dashboard. Written for you by `poller/enroll.py`; see [`cloud/`](cloud/README.md) |
| `SINKS` | (Optional) `influx`, `cloud`, or both. Defaults to whichever are configured |

## Running on a Raspberry Pi

This stack runs comfortably on a Raspberry Pi 4 (4GB+, 64-bit OS). A few things worth knowing:

- **You need the 64-bit OS.** Run `uname -m` — it must print `aarch64`. InfluxDB 2.x has no maintained image for 32-bit ARM. Reflash with Raspberry Pi OS (64-bit) or Ubuntu Server 24.04 LTS (arm64) if needed.
- **Install Docker:**
  ```bash
  curl -sSL https://get.docker.com | sh
  sudo usermod -aG docker $USER   # log out/in afterward
  sudo apt install -y docker-compose-plugin
  ```
- **RAM**: comfortable on 4GB/8GB models; a 2GB Pi may struggle once Grafana is actively rendering.
- **SD card wear**: InfluxDB writes fairly often. For long-term unattended use, consider pointing the `influxdb-data` volume at a USB SSD instead of the SD card.
- **If containers exit with code 159** (`SIGSYS`): this is a known seccomp/kernel interaction on some Pi kernels, not a bug in this project. `docker-compose.yml` already sets `security_opt: seccomp:unconfined` on the affected services to work around it.

## Known limitations

- **Per-trip energy (kWh used/regenerated on a single trip)** isn't reliably exposed by the underlying API — only distance, speed, and time per trip. Energy is available at daily resolution instead (see the "Daily Energy Breakdown" panels).
- **`power_consumption_30d` (the 30-day rolling efficiency figure) is a Europe-only feature** of the underlying API, per its own documentation — it may not populate for US/CA accounts.
- **Lifetime cumulative energy counters** have been reported by some users to show unit/scaling oddities on certain cars — treat them as directional rather than exact.
- Some fields (energy breakdown, charge limits, departure schedule) vary by brand/region/car generation. Run `dump_fields.py` (see Quick Start) if a panel ever shows unexpected empty data — it'll tell you plainly whether a field is missing for your account rather than failing silently.

## Ideas for extending this

- **Cost tracking**: multiply daily `consumed_kwh` by your electricity tariff.
- **Efficiency vs. temperature**: correlate kWh/100km against outside temperature (e.g. via [Open-Meteo](https://open-meteo.com/), no API key needed).
- **Alerting**: a Grafana alert if the 12V battery % drops below a threshold, or if SoC hasn't moved in N days (parked-and-forgotten / dead 12V risk).

## Project layout

```
docker-compose.yml
.env.example
poller/
  Dockerfile
  requirements.txt
  common.py           # env loading, region/brand mapping, VehicleManager setup
  sinks.py            # where readings go: local InfluxDB and/or the hosted API
  enroll.py           # one-time: trade an enrollment code for an agent API key
  dump_fields.py            # run once - dumps your account's raw field names
  main.py               # scheduler: status + trip + energy polling
grafana/
  provisioning/
    datasources/datasource.yml
    dashboards/dashboards.yml
  dashboards/ioniq5-overview.json
cloud/                # optional hosted API: multi-tenant ingest + query
  app/
  tests/
docker-compose.cloud.yml
```

## Contributing

Issues and pull requests are welcome — especially reports of field names that differ for your brand/region/car generation, since that's the hardest thing to test without a wide range of accounts.

## License

No license file is currently included in this repository, which means default copyright applies (all rights reserved) even though the source is public. If you'd like to reuse or modify this project, please open an issue first, or add a license of your choosing before republishing.
