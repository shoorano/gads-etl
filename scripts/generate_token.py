"""Interactive helper for generating Google Ads refresh tokens without touching .env files."""
import time
import webbrowser
from typing import List
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

import typer
from google_auth_oauthlib.flow import InstalledAppFlow

from api.google_ads.google_ads_get_client import GoogleAdsGetClient
from common.database import Database

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/content",
]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_REDIRECT_PATH = "/handle-authentication"
OAUTH_TIMEOUT_SECONDS = 300

app = typer.Typer(add_completion=False, help=__doc__)


class _OAuthRedirectApp:
    """Minimal WSGI app to capture OAuth callback parameters."""

    def __init__(self, redirect_path: str) -> None:
        self.redirect_path = redirect_path
        self.handled = False
        self.code: str | None = None
        self.state: str | None = None
        self.error: str | None = None
        self.expected_state: str | None = None

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or ""
        if path != self.redirect_path:
            start_response(
                "404 Not Found",
                [("Content-Type", "text/plain; charset=utf-8")],
            )
            return [b"Not Found"]

        self.handled = True
        query = parse_qs(environ.get("QUERY_STRING", ""))
        self.code = (query.get("code") or [None])[0]
        self.state = (query.get("state") or [None])[0]
        self.error = (query.get("error") or [None])[0]

        status = "200 OK"
        message = "Authentication complete. You may close this window."
        if self.error:
            status = "400 Bad Request"
            message = f"Authentication failed: {self.error}"
        elif not self.code:
            status = "400 Bad Request"
            message = "Missing `code` parameter in OAuth response."

        start_response(
            status,
            [
                ("Content-Type", "text/html; charset=utf-8"),
                ("Cache-Control", "no-store"),
            ],
        )
        html = f"<html><body><p>{message}</p></body></html>"
        return [html.encode("utf-8")]


def _run_local_oauth_flow(
    flow: InstalledAppFlow,
    host: str,
    port: int,
    redirect_path: str,
) -> None:
    """Run OAuth flow using a custom redirect path."""
    redirect_uri = f"http://{host}:{port}{redirect_path}"
    app = _OAuthRedirectApp(redirect_path)
    server = make_server(host, port, app)
    server.timeout = 1
    flow.redirect_uri = redirect_uri

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    app.expected_state = state

    typer.echo("Opening browser for OAuth consent...")
    if not webbrowser.open(authorization_url, new=1, autoraise=True):
        typer.echo("Please open the following URL in your browser:")
    typer.echo(authorization_url)

    deadline = time.time() + OAUTH_TIMEOUT_SECONDS
    try:
        while not app.handled:
            if time.time() > deadline:
                typer.secho(
                    "Timed out waiting for the OAuth redirect.",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(code=1)
            server.handle_request()
    finally:
        server.server_close()

    if app.error:
        typer.secho(f"OAuth error: {app.error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if app.expected_state and app.expected_state != app.state:
        typer.secho(
            "State mismatch detected in OAuth redirect.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    if not app.code:
        typer.secho(
            "OAuth redirect did not contain an authorization code.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    flow.fetch_token(code=app.code)


def _persist_refresh_token(google_account_id: str, refresh_token: str) -> None:
    query = """
        update google_accounts
        set refresh_token = :refresh_token
        where id = :google_account_id
    """
    Database().execute_parameterised_query(
        base_query=query,
        parameters={
            "refresh_token": refresh_token,
            "google_account_id": google_account_id,
        },
    )


@app.command()
def main(
    google_id: str = typer.Option(
        ...,
        "--google-id",
        help="google_accounts.id value to store the refresh token against",
    ),
    scopes: List[str] = typer.Option(
        DEFAULT_SCOPES,
        help="OAuth scopes to request",
    ),
    port: int = typer.Option(
        DEFAULT_PORT,
        help="Local port for the OAuth redirect listener",
    ),
) -> None:
    """Launch OAuth flow, print the refresh token, and store it in google_accounts."""
    config = GoogleAdsGetClient.oauth_config()
    client_id = config["client_id"]
    client_secret = config["client_secret"]
    redirect_uri = f"http://{DEFAULT_HOST}:{port}{DEFAULT_REDIRECT_PATH}"
    flow = InstalledAppFlow.from_client_config(
        client_config={
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": [redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=scopes,
    )
    _run_local_oauth_flow(
        flow=flow,
        host=DEFAULT_HOST,
        port=port,
        redirect_path=DEFAULT_REDIRECT_PATH,
    )
    refresh_token = flow.credentials.refresh_token
    if not refresh_token:
        typer.secho(
            "No refresh token returned; ensure offline access is enabled.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo("Refresh token acquired:\n")
    typer.echo(refresh_token)

    _persist_refresh_token(google_id, refresh_token)
    typer.echo(
        f"\nStored refresh token for google_account_id={google_id} "
        f"using client_id={client_id}."
    )


if __name__ == "__main__":  # pragma: no cover
    app()
