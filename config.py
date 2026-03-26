"""Configuration — loaded from .env or environment variables."""

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
            github_token=os.getenv("GITHUB_TOKEN", ""),
            github_repo=os.getenv("GITHUB_REPO", ""),
        )


config = Config.load()
