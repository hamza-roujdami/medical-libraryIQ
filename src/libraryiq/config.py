from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIBRARYIQ_", env_file=".env", extra="ignore")

    model_provider: Literal["ollama"] = "ollama"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # Sent to Crossref, PubMed and Unpaywall as their requested contact address.
    contact_email: str

    librarian_email: str = "librarian@example.org"
    approval_base_url: str = "http://localhost:8000"
    # Replaced by the signed-in user once the agent runs behind Teams sign-in.
    requester: str = "demo.user@example.org"
    database_path: str = "libraryiq.db"
