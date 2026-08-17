"""Trade a one-time enrollment code from the web app for this agent's API key.

    python enroll.py --url https://cloud.example.com --code ABCD-EFGH-JKLM

Writes CLOUD_INGEST_URL / CLOUD_AGENT_KEY into the root .env so the poller
starts forwarding readings on its next run. Bluelink credentials stay in that
same .env, on this machine, and are never sent anywhere but Hyundai/Kia.
"""

import argparse
import sys
from pathlib import Path

import requests

ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"


def enroll(url: str, code: str, agent_name: str) -> dict:
    response = requests.post(
        f"{url.rstrip('/')}/v1/agents/enroll",
        json={"code": code, "agent_name": agent_name},
        timeout=30,
    )
    if response.status_code != 201:
        detail = response.json().get("detail", response.text)
        raise SystemExit(f"Enrollment failed ({response.status_code}): {detail}")
    return response.json()


def upsert_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(values)

    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"

    if remaining:
        lines.append("")
        lines.append("# --- Hosted dashboard (written by enroll.py) ---")
        lines += [f"{k}={v}" for k, v in remaining.items()]

    path.write_text("\n".join(lines) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Base URL of the cloud API")
    parser.add_argument(
        "--code", required=True, help="Enrollment code from the web app"
    )
    parser.add_argument("--agent-name", default="poller")
    parser.add_argument(
        "--env-file", default=str(ROOT_ENV), help="Where to write the credentials"
    )
    args = parser.parse_args(argv)

    result = enroll(args.url, args.code, args.agent_name)
    upsert_env(
        Path(args.env_file),
        {
            "CLOUD_INGEST_URL": args.url.rstrip("/"),
            "CLOUD_AGENT_KEY": result["api_key"],
        },
    )
    print(f"Enrolled as agent {result['agent_id']} for vehicle {result['vehicle_id']}.")
    print(f"Wrote CLOUD_INGEST_URL and CLOUD_AGENT_KEY to {args.env_file}.")
    print("Restart the poller (docker compose up -d) to start forwarding readings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
