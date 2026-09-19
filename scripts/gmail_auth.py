"""One-off helper for MA-08: sign in as the sandbox Gmail account and print a refresh token.

Run with GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in the environment (a Desktop-app OAuth client).
Nothing is written to disk. Copy the printed token into the GMAIL_REFRESH_TOKEN setting on the host.
"""

import base64
import hashlib
import http.server
import os
import secrets
import sys
import urllib.parse
import webbrowser

import httpx

SCOPES = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly"
PORT = 8765


def main() -> int:
    client_id, client_secret = os.environ.get("GMAIL_CLIENT_ID"), os.environ.get("GMAIL_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET first.")
        return 1
    redirect = f"http://127.0.0.1:{PORT}/"
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    got: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            got.update({k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"You can close this tab and return to the terminal.")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    print("Opening the browser. Sign in as the sandbox Gmail account and allow access.")
    print("If it does not open, visit:\n" + url)
    webbrowser.open(url)
    server.handle_request()
    if got.get("state") != state or "code" not in got:
        print("Sign-in failed:", got.get("error", "state mismatch"))
        return 1
    r = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": got["code"],
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
        },
        timeout=30,
    )
    body = r.json()
    if "refresh_token" not in body:
        print("Google did not return a refresh token:", body.get("error_description") or body.get("error"))
        return 1
    print("\nGMAIL_REFRESH_TOKEN=" + body["refresh_token"])
    print("Testing-mode tokens expire after 7 days. Repeat this on Sunday before judging.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
