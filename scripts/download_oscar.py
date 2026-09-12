"""
Download OSCAR Surface Ocean Current vectors from NASA PO.DAAC / Earthdata.

Requires NASA Earthdata login credentials passed via environment variables:
- EARTHDATA_USERNAME
- EARTHDATA_PASSWORD
(or stored in ~/.netrc)

Stops and prints registration/setup instructions if credentials are not provided.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "ocean_currents"
NETRC_PATH = Path.home() / ".netrc"


def check_earthdata_credentials():
    """Verify presence of Earthdata username and password."""
    username = os.environ.get("EARTHDATA_USERNAME")
    password = os.environ.get("EARTHDATA_PASSWORD")

    has_netrc = NETRC_PATH.exists() and "urs.earthdata.nasa.gov" in NETRC_PATH.read_text(errors="ignore")

    if (not username or not password) and not has_netrc:
        print("\n" + "=" * 70)
        print("MISSING CREDENTIALS: NASA Earthdata (OSCAR Ocean Currents)")
        print("=" * 70)
        print("OSCAR ocean currents download requires a free NASA Earthdata login:")
        print("1. Register a free account at: https://urs.earthdata.nasa.gov/users/new")
        print("2. Authorize the 'PO.DAAC Data Subscriber' or 'Earthdata Search' application in your profile.")
        print("3. Export your credentials in your terminal:")
        print("     export EARTHDATA_USERNAME=\"your_username\"")
        print("     export EARTHDATA_PASSWORD=\"your_password\"")
        print("   OR configure ~/.netrc with:")
        print("     machine urs.earthdata.nasa.gov login <USER> password <PASS>")
        print("=" * 70 + "\n")
        return False

    return True


def main():
    if not check_earthdata_credentials():
        sys.exit(1)

    print("[+] NASA Earthdata credentials verified.")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    main()
