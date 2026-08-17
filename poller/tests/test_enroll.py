import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from enroll import upsert_env


def test_upsert_env_replaces_existing_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("BLUELINK_USERNAME=me\nCLOUD_AGENT_KEY=old\n")

    upsert_env(
        env, {"CLOUD_INGEST_URL": "https://cloud.example", "CLOUD_AGENT_KEY": "new"}
    )

    assert "CLOUD_AGENT_KEY=new" in env.read_text()
    assert "CLOUD_AGENT_KEY=old" not in env.read_text()
    assert "BLUELINK_USERNAME=me" in env.read_text()


def test_upsert_env_appends_when_missing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("BLUELINK_USERNAME=me\n")

    upsert_env(env, {"CLOUD_INGEST_URL": "https://cloud.example"})

    assert env.read_text().splitlines()[-1] == "CLOUD_INGEST_URL=https://cloud.example"
