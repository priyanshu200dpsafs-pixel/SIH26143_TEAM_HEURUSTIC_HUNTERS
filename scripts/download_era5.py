"""
Download ERA5 10m u/v surface wind components from Copernicus Climate Data Store (CDS).

Requires CDS account credentials configured in ~/.cdsapirc.
Stops and prints registration/setup instructions if ~/.cdsapirc is missing.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "weather"
CDSAPIRC_PATH = Path.home() / ".cdsapirc"


def check_cds_config():
    """Verify presence and non-emptiness of ~/.cdsapirc."""
    if not CDSAPIRC_PATH.exists() or CDSAPIRC_PATH.stat().st_size == 0:
        print("\n" + "=" * 70)
        print("MISSING CONFIGURATION: Copernicus Climate Data Store (ERA5)")
        print("=" * 70)
        print("ERA5 wind data requires an active CDS account and API credentials in ~/.cdsapirc.")
        print("1. Register a free account at: https://cds.climate.copernicus.eu")
        print("2. Log in and navigate to your user profile (top right).")
        print("3. Copy your Personal Access Token (API key).")
        print("4. Create the file ~/.cdsapirc with the following format:")
        print("     url: https://cds.climate.copernicus.eu/api")
        print("     key: <YOUR_PERSONAL_ACCESS_TOKEN>")
        print("5. Accept the ERA5 Terms of Use on the CDS portal.")
        print("=" * 70 + "\n")
        return False
    return True


def main():
    if not check_cds_config():
        sys.exit(1)

    print("[+] Found ~/.cdsapirc configuration.")
    try:
        import cdsapi
    except ImportError:
        print("[!] cdsapi library not found. Install it via: pip install cdsapi")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    c = cdsapi.Client()
    print("[+] Successfully initialized CDS API client.")


if __name__ == "__main__":
    main()
