"""Configuration — loaded from .env or environment variables."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    output_dir: Path = Path("outputs")
    data_dir: Path = Path("data")
    kaggle_username: str = ""
    kaggle_key: str = ""
    github_token: str = ""
    github_repo: str = ""

    @classmethod
    def load(cls) -> "Config":
        return cls(
            output_dir=Path(os.getenv("OUTPUT_DIR", "outputs")),
            data_dir=Path(os.getenv("DATA_DIR", "data")),
            kaggle_username=os.getenv("KAGGLE_USERNAME", ""),
            kaggle_key=os.getenv("KAGGLE_KEY", ""),
            github_token=os.getenv("GH_PAT", "") or os.getenv("GITHUB_TOKEN", ""),
            github_repo=os.getenv("GITHUB_REPO", ""),
        )

    def ensure_kaggle_json(self) -> None:
        """Write ~/.kaggle/kaggle.json from .env credentials, overwriting if they differ.

        kagglesdk's KaggleClient() reads basic-auth credentials ONLY from
        ~/.kaggle/kaggle.json — it ignores KAGGLE_USERNAME / KAGGLE_KEY env vars.
        The Benchmark Tasks API rejects Bearer auth (used when api_token= is passed
        explicitly), so we must ensure kaggle.json is up-to-date before KaggleClient().
        """
        if not self.kaggle_username or not self.kaggle_key:
            return
        kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
        desired = {"username": self.kaggle_username, "key": self.kaggle_key}
        if kaggle_json.exists():
            try:
                existing = json.loads(kaggle_json.read_text())
                if existing.get("username") == self.kaggle_username and existing.get("key") == self.kaggle_key:
                    return
            except Exception:
                pass
        kaggle_json.parent.mkdir(mode=0o700, exist_ok=True)
        kaggle_json.write_text(json.dumps(desired))
        kaggle_json.chmod(0o600)


config = Config.load()
