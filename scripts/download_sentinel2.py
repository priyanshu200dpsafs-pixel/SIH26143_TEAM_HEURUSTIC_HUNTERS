"""
Download Sentinel-2 Optical L2A imagery from Copernicus Data Space Ecosystem (CDSE).

Requires OAuth2 client credentials via environment variables:
- CDSE_CLIENT_ID (or CLIENT_ID)
- CDSE_CLIENT_SECRET (or CLIENT_SECRET)

Stops and prints registration/setup instructions if credentials are not provided.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "optical_images"

AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"


def check_credentials():
    """Verify presence of Copernicus Data Space Ecosystem credentials."""
    client_id = os.environ.get("CDSE_CLIENT_ID") or os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CDSE_CLIENT_SECRET") or os.environ.get("CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\n" + "=" * 70)
        print("MISSING CREDENTIALS: Copernicus Data Space Ecosystem (Sentinel-2)")
        print("=" * 70)
        print("To download real Sentinel-2 L2A optical scenes, please set up OAuth2 credentials:")
        print("1. Register for a free account at: https://dataspace.copernicus.eu")
        print("2. Navigate to your User Profile -> 'API Keys' / 'OAuth Clients'.")
        print("3. Generate a new Client ID and Client Secret.")
        print("4. Export them in your terminal before running this script:")
        print("     export CDSE_CLIENT_ID=\"your_client_id_here\"")
        print("     export CDSE_CLIENT_SECRET=\"your_client_secret_here\"")
        print("=" * 70 + "\n")
        return None, None

    return client_id, client_secret


def get_access_token(client_id: str, client_secret: str) -> str:
    """Acquire bearer token via OAuth2 client_credentials flow."""
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    req = urllib.request.Request(AUTH_URL, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res["access_token"]


def main():
    client_id, client_secret = check_credentials()
    if not client_id or not client_secret:
        sys.exit(1)

    print("[*] Authenticating with Copernicus Data Space Ecosystem...")
    token = get_access_token(client_id, client_secret)
    print("[+] Successfully authenticated. Ready to query Sentinel-2 L2A tiles.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Target query matching SAR coordinates
    print(f"[+] Output directory ready: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
