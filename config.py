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
        """Write ~/.kaggle/kaggle.json from .env credentials if the file doesn't exist.

        kagglesdk's KaggleClient() reads basic-auth credentials ONLY from
        ~/.kaggle/kaggle.json — it ignores KAGGLE_USERNAME / KAGGLE_KEY env vars.
        The Benchmark Tasks API rejects Bearer auth (used when api_token= is passed
        explicitly), so we must ensure kaggle.json exists before calling KaggleClient().

        This is a no-op if kaggle.json already exists (we never overwrite existing creds).
        """
        if not self.kaggle_username or not self.kaggle_key:
            return
        kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
        if kaggle_json.exists():
            return
        kaggle_json.parent.mkdir(mode=0o700, exist_ok=True)
        kaggle_json.write_text(json.dumps({
            "username": self.kaggle_username,
            "key": self.kaggle_key,
        }))
        kaggle_json.chmod(0o600)


config = Config.load()
