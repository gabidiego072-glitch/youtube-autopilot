#!/usr/bin/env python3
"""One-time YouTube authorization: gets the refresh token the pipeline uses to upload unattended.

Run it ONCE on your own computer (it opens your browser):

    python scripts/youtube_auth.py                    # scopes: upload, readonly, analytics
    python scripts/youtube_auth.py --with-comments    # also allow posting comments

It asks for the OAuth client ID and secret of a "Desktop app" client (or reads YOUTUBE_CLIENT_ID /
YOUTUBE_CLIENT_SECRET from the environment), opens Google's consent page, receives the answer on
http://127.0.0.1:<port> (loopback + PKCE) and saves the refresh token to a private file
(~/.youtube-autopilot/refresh_token, permissions 600). The token is never printed.
Then store it as the GitHub secret YOUTUBE_REFRESH_TOKEN:

    gh secret set YOUTUBE_REFRESH_TOKEN < ~/.youtube-autopilot/refresh_token

(or pass --set-github-secret to do it automatically when the GitHub CLI is installed and logged in).
"""

from __future__ import annotations

import argparse
import getpass
import http.server
import os
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.services.youtube.oauth import DEFAULT_SCOPES, build_auth_url, exchange_code, pkce_pair, scope_urls  # noqa: E402

TOKEN_FILE = Path.home() / ".youtube-autopilot" / "refresh_token"


class _Handler(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self) -> None:  # noqa: N802 - stdlib name
        query = parse_qs(urlparse(self.path).query)
        if "code" not in query and "error" not in query:
            self.send_response(404)
            self.end_headers()
            return
        _Handler.result = {k: v[0] for k, v in query.items()}
        ok = "code" in query
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        message = "Autorizado. Ya puedes cerrar esta pestaña." if ok else "Autorización cancelada o rechazada."
        self.wfile.write(f"<html><body><h2>{message}</h2></body></html>".encode())

    def log_message(self, *args) -> None:  # keep the terminal clean (the URL holds the code)
        return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--with-comments", action="store_true", help="also request youtube.force-ssl (comments)")
    parser.add_argument("--output", type=Path, default=TOKEN_FILE)
    parser.add_argument("--set-github-secret", action="store_true", help="run `gh secret set YOUTUBE_REFRESH_TOKEN`")
    parser.add_argument("--no-browser", action="store_true", help="print the URL instead of opening the browser")
    args = parser.parse_args()

    client_id = os.environ.get("YOUTUBE_CLIENT_ID") or input("OAuth client ID (Desktop app): ").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET") or getpass.getpass("OAuth client secret (hidden): ")
    scopes = scope_urls([*DEFAULT_SCOPES, *(["comments"] if args.with_comments else [])])

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    redirect_uri = f"http://127.0.0.1:{server.server_port}"
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    url = build_auth_url(client_id, redirect_uri, scopes, state, challenge)

    def serve() -> None:  # ignore stray requests (favicon...) until Google's redirect arrives
        while not _Handler.result:
            server.handle_request()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    print("Abre esta dirección, elige la cuenta de Google del CANAL y acepta los permisos:\n")
    print(url + "\n")
    if not args.no_browser:
        webbrowser.open(url)
    print("Si Google avisa de «Google no ha verificado esta aplicación»: es tu propia app;")
    print("pulsa «Configuración avanzada» → «Ir a … (no seguro)» para continuar.\n")
    thread.join(timeout=600)
    server.server_close()

    answer = _Handler.result
    if not answer:
        print("No llegó respuesta en 10 minutos.", file=sys.stderr)
        return 1
    if answer.get("error") or answer.get("state") != state:
        print(f"Autorización no completada: {answer.get('error', 'state mismatch')}", file=sys.stderr)
        return 1

    with httpx.Client(timeout=30) as client:
        tokens = exchange_code(client, client_id, client_secret, answer["code"], redirect_uri, verifier)
    granted = set(tokens.get("scope", "").split())
    missing = [s for s in scopes if s not in granted]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.touch(mode=0o600, exist_ok=True)
    os.chmod(args.output, 0o600)
    args.output.write_text(tokens["refresh_token"])
    print(f"Refresh token guardado en {args.output} (no se muestra).")
    if missing:
        print("AVISO: no se concedieron estos permisos (marca todas las casillas):", *missing, sep="\n  ")

    if args.set_github_secret:
        if not shutil.which("gh"):
            print("GitHub CLI (gh) no está instalado; guarda el secreto a mano.", file=sys.stderr)
            return 1
        with args.output.open() as handle:
            subprocess.run(["gh", "secret", "set", "YOUTUBE_REFRESH_TOKEN"], stdin=handle, check=True)
        print("Secreto YOUTUBE_REFRESH_TOKEN actualizado en GitHub.")
    else:
        print(f"Siguiente paso:  gh secret set YOUTUBE_REFRESH_TOKEN < {args.output}")
    print("Comprueba que funciona con:  python scripts/autopilot.py youtube-check")
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
