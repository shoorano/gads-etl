"""Interactive helper for generating and storing Google Ads refresh tokens."""
import os
from pathlib import Path
from typing import List

import typer
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/content",
]

app = typer.Typer(add_completion=False, help=__doc__)


def _load_default_env() -> None:
    for candidate in (".env", ".env.test"):
        path = Path(candidate)
        if path.exists():
            load_dotenv(dotenv_path=path, override=True)


def _build_client_config(client_id: str, client_secret: str) -> dict:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [
                "http://localhost:8080/",
            ],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _persist_env_value(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content: List[str] = []
    if path.exists():
        content = path.read_text().splitlines()
    replaced = False
    for idx, line in enumerate(content):
        if not line or line.strip().startswith("#"):
            continue
        if line.split("=", 1)[0] == key:
            content[idx] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        content.append(f"{key}={value}")
    path.write_text("\n".join(content) + "\n")


def _resolve_prefix(env_file: Path) -> str:
    if "test" in env_file.name:
        return "TEST_GOOGLE_ADS"
    return "GOOGLE_ADS"


def _infer_env_key(env_file: Path, env_key: str | None) -> str:
    if env_key:
        return env_key
    prefix = _resolve_prefix(env_file)
    return f"{prefix}_REFRESH_TOKEN"


@app.command()
def main(
    client_id: str
    | None = typer.Option(
        None,
        help="OAuth client ID (defaults to GOOGLE_ADS_CLIENT_ID from .env/.env.test)",
    ),
    client_secret: str
    | None = typer.Option(
        None,
        help="OAuth client secret (defaults to GOOGLE_ADS_CLIENT_SECRET from .env/.env.test)",
    ),
    scopes: List[str] = typer.Option(
        DEFAULT_SCOPES,
        help="OAuth scopes to request",
    ),
    env_file: Path = typer.Option(
        Path(".env"),
        help="Env file to update with the refresh token",
    ),
    env_key: str
    | None = typer.Option(
        None,
        help="Environment variable name to store the refresh token under",
    ),
    port: int = typer.Option(
        8080,
        help="Local port for the OAuth consent redirect (passed to run_local_server)",
    ),
) -> None:
    """Launch OAuth flow, print the refresh token, and optionally save it."""
    _load_default_env()
    prefix = _resolve_prefix(env_file)
    client_id = client_id or os.getenv(f"{prefix}_CLIENT_ID")
    client_secret = client_secret or os.getenv(f"{prefix}_CLIENT_SECRET")
    if not client_id or not client_secret:
        typer.secho(
            "Missing client credentials. Provide --client-id/--client-secret or set "
            "GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET in your env files.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    flow = InstalledAppFlow.from_client_config(
        client_config=_build_client_config(client_id, client_secret),
        scopes=scopes,
    )
    typer.echo("Opening browser for OAuth consent...")
    credentials = flow.run_local_server(port=port, prompt="consent")
    refresh_token = credentials.refresh_token
    typer.echo("Refresh token acquired:\n")
    typer.echo(refresh_token)

    env_key_resolved = _infer_env_key(env_file, env_key)
    if refresh_token:
        _persist_env_value(env_file, env_key_resolved, refresh_token)
        typer.echo(f"\nSaved refresh token to {env_file} ({env_key_resolved})")
    else:
        typer.echo(
            "No refresh token returned; ensure offline access is enabled.", err=True
        )


if __name__ == "__main__":  # pragma: no cover
    app()
