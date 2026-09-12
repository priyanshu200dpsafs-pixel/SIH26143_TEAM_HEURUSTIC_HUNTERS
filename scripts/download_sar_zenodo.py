"""
Query and Download Sentinel-1 SAR Oil Spill Training Dataset from Zenodo.

Uses Zenodo REST API (https://zenodo.org/api/records) with curl-backed requests
to navigate Cloudflare TLS protections.
"""

import os
import sys
import json
import subprocess
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "sar_images"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def search_zenodo(query: str = "Sentinel-1 SAR oil spill dataset segmentation", size: int = 5):
    """Query Zenodo REST API."""
    encoded_q = urllib.parse.quote_plus(query)
    url = f"https://zenodo.org/api/records?q={encoded_q}&size={size}"
    print(f"[*] Querying Zenodo REST API: {url}")
    
    cmd = ["curl", "-s", "-H", f"User-Agent: {USER_AGENT}", url]
    out = subprocess.check_output(cmd)
    data = json.loads(out.decode("utf-8"))
    return data.get("hits", {}).get("hits", [])


def download_stream(url: str, dest_path: Path):
    """Download a file with curl streaming."""
    print(f"[*] Downloading: {url} -> {dest_path}")
    cmd = [
        "curl",
        "-L",
        "-H", f"User-Agent: {USER_AGENT}",
        "--progress-bar",
        "-o", str(dest_path),
        url,
    ]
    subprocess.run(cmd, check=True)
    size_mb = dest_path.stat().st_size / (1024 * 1024)
    print(f"[+] Download complete: {dest_path.name} ({size_mb:.2f} MB)")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    hits = search_zenodo()
    print(f"\n[+] Zenodo records found ({len(hits)} results):")
    for i, h in enumerate(hits, 1):
        rec_id = h.get("id")
        title = h.get("metadata", {}).get("title")
        files = h.get("files", [])
        total_mb = sum(f.get("size", 0) for f in files) / (1024 * 1024)
        print(f"\n[{i}] Record ID: {rec_id} | Title: {title}")
        print(f"    Total size: {total_mb:.2f} MB ({len(files)} files)")
        for f in files:
            print(f"     -> {f.get('key')} ({f.get('size', 0)/(1024*1024):.2f} MB)")


if __name__ == "__main__":
    main()
