"""
WHOOP band connector.

Pulls your sleep, recovery, strain (cycle), and workout data from the
WHOOP v2 API and saves it as CSV files in ./whoop_data/ so it can be
loaded with pandas and analysed (e.g. with Claude).

One-time setup:
  1. Go to https://developer-dashboard.whoop.com and create an app.
  2. Add this exact Redirect URI to the app:  http://localhost:8765/callback
  3. Enable all the read scopes (recovery, cycles, sleep, workout,
     profile, body measurement) plus "offline".
  4. Export your credentials before running:
       export WHOOP_CLIENT_ID="your-client-id"
       export WHOOP_CLIENT_SECRET="your-client-secret"

Usage:
  python whoop_connector.py              # last 90 days
  python whoop_connector.py --days 365   # last year
  python whoop_connector.py --all        # everything WHOOP has on you

The first run opens your browser to log in to WHOOP. Tokens are cached
in .whoop_tokens.json and refreshed automatically afterwards.
"""

import argparse
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
API_BASE = "https://api.prod.whoop.com/developer"

REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = (
    "offline read:recovery read:cycles read:sleep "
    "read:workout read:profile read:body_measurement"
)

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".whoop_tokens.json")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whoop_data")


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whoop_credentials.json")


def get_credentials():
    client_id = os.environ.get("WHOOP_CLIENT_ID")
    client_secret = os.environ.get("WHOOP_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret

    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE) as f:
            creds = json.load(f)
        if creds.get("client_id") and creds.get("client_secret"):
            return creds["client_id"], creds["client_secret"]

    print("No WHOOP credentials found - let's save them now.")
    print("(They come from your app at https://developer-dashboard.whoop.com)")
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    if not client_id or not client_secret:
        sys.exit("Both Client ID and Client Secret are required.")
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump({"client_id": client_id, "client_secret": client_secret}, f, indent=2)
    try:
        os.chmod(CREDENTIALS_FILE, 0o600)
    except OSError:
        pass
    print(f"Saved to {CREDENTIALS_FILE} (gitignored).\n")
    return client_id, client_secret


def wait_for_auth_code(expected_state):
    """Run a tiny local web server until WHOOP redirects back with the code."""
    result = {}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            if params.get("state", [None])[0] != expected_state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch - please retry.")
                return
            if "code" in params:
                result["code"] = params["code"][0]
                message = b"WHOOP connected! You can close this tab and return to the terminal."
            else:
                result["error"] = params.get("error_description", params.get("error", ["unknown"]))[0]
                message = b"Authorization failed - check the terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(message)

        def log_message(self, *args):
            pass  # keep the terminal quiet

    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        while "code" not in result and "error" not in result:
            time.sleep(0.2)
    finally:
        server.shutdown()
    if "error" in result:
        sys.exit(f"WHOOP authorization failed: {result['error']}")
    return result["code"]


def manual_auth_code(url, expected_state):
    """Phone-friendly flow: user opens the link anywhere, then pastes the
    redirect URL (or just the code) back into the terminal.

    After approving on WHOOP you land on a localhost page that fails to
    load - that's expected. The code we need is in that page's address bar.
    """
    print("Open this link (on any device) and log in to WHOOP:\n")
    print(f"  {url}\n")
    print("After you approve, your browser will try to open a localhost page")
    print("that won't load - that's fine. Copy the FULL URL from the address")
    print("bar (it contains ?code=...) and paste it here.\n")
    pasted = input("Paste the redirect URL (or just the code): ").strip()
    if "code=" in pasted:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
        if params.get("state", [expected_state])[0] != expected_state:
            sys.exit("State mismatch - please rerun and use the freshly printed link.")
        return params["code"][0]
    return pasted  # assume they pasted the bare code


def authorize(client_id, client_secret, manual=False):
    """Full login flow. Returns a token dict."""
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    if manual:
        code = manual_auth_code(url, state)
    else:
        print("Opening your browser to log in to WHOOP...")
        print(f"If it doesn't open, visit:\n  {url}\n")
        webbrowser.open(url)
        code = wait_for_auth_code(state)

    response = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
    })
    response.raise_for_status()
    return response.json()


def refresh(client_id, client_secret, refresh_token):
    response = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "offline",
    })
    response.raise_for_status()
    return response.json()


def save_tokens(tokens):
    tokens["saved_at"] = time.time()
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def get_access_token(manual=False):
    """Return a valid access token, refreshing or re-authorizing as needed."""
    client_id, client_secret = get_credentials()

    tokens = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            tokens = json.load(f)

    if tokens:
        expires_at = tokens.get("saved_at", 0) + tokens.get("expires_in", 0)
        if time.time() < expires_at - 60:
            return tokens["access_token"]
        if tokens.get("refresh_token"):
            try:
                tokens = refresh(client_id, client_secret, tokens["refresh_token"])
                save_tokens(tokens)
                return tokens["access_token"]
            except requests.HTTPError:
                print("Token refresh failed, starting a fresh login...")

    tokens = authorize(client_id, client_secret, manual=manual)
    save_tokens(tokens)
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# API fetching
# ---------------------------------------------------------------------------

def api_get(path, token, params=None):
    """GET one API page, retrying politely if WHOOP rate-limits us."""
    while True:
        response = requests.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        )
        if response.status_code == 429:
            wait = int(response.headers.get("Retry-After", 10))
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()


def fetch_collection(path, token, start=None):
    """Fetch every page of a paginated collection endpoint."""
    records = []
    params = {"limit": 25}
    if start:
        params["start"] = start
    while True:
        page = api_get(path, token, params)
        records.extend(page.get("records", []))
        next_token = page.get("next_token")
        if not next_token:
            break
        params["nextToken"] = next_token
        print(f"  ...{len(records)} records so far")
    return records


# ---------------------------------------------------------------------------
# Flattening & saving
# ---------------------------------------------------------------------------

def to_csv(records, filename):
    path = os.path.join(DATA_DIR, filename)
    if not records:
        print(f"  {filename}: no records, skipped")
        return None
    df = pd.json_normalize(records)
    # millisecond durations are awkward to read - add hour versions alongside
    for col in [c for c in df.columns if c.endswith("_milli")]:
        df[col.replace("_milli", "_hours")] = df[col] / 3_600_000
    df.to_csv(path, index=False)
    print(f"  {filename}: {len(df)} rows")
    return df


def main():
    parser = argparse.ArgumentParser(description="Pull WHOOP data to CSV files.")
    parser.add_argument("--days", type=int, default=90, help="how many days back to fetch (default 90)")
    parser.add_argument("--all", action="store_true", help="fetch the full history instead")
    parser.add_argument("--manual", action="store_true",
                        help="phone/headless login: prints the WHOOP link and lets you paste the code back")
    args = parser.parse_args()

    start = None
    if not args.all:
        start = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"Fetching WHOOP data from the last {args.days} days...")
    else:
        print("Fetching your full WHOOP history (this can take a while)...")

    token = get_access_token(manual=args.manual)
    os.makedirs(DATA_DIR, exist_ok=True)

    profile = api_get("/v2/user/profile/basic", token)
    body = api_get("/v2/user/measurement/body", token)
    with open(os.path.join(DATA_DIR, "profile.json"), "w") as f:
        json.dump({"profile": profile, "body_measurements": body}, f, indent=2)
    print(f"Connected as {profile.get('first_name', '')} {profile.get('last_name', '')}".strip())

    print("Sleep:")
    to_csv(fetch_collection("/v2/activity/sleep", token, start), "sleep.csv")
    print("Recovery:")
    to_csv(fetch_collection("/v2/recovery", token, start), "recovery.csv")
    print("Cycles (daily strain):")
    to_csv(fetch_collection("/v2/cycle", token, start), "cycles.csv")
    print("Workouts:")
    to_csv(fetch_collection("/v2/activity/workout", token, start), "workouts.csv")

    print(f"\nDone. Files are in {DATA_DIR}/")
    print("Load them with pandas, e.g.:")
    print("  df = pd.read_csv('whoop_data/sleep.csv', parse_dates=['start', 'end'])")


if __name__ == "__main__":
    main()
