"""
Resumable chunk downloader and automatic unpacker for Zenodo SOS images.zip.
Uses HTTP Range requests so connection drops automatically resume without losing downloaded bytes.
"""

import os
import sys
import time
import zipfile
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOS_DIR = PROJECT_ROOT / "data" / "sar_images" / "sos_dataset"
TARGET_FILE = SOS_DIR / "images.zip"
EXTRACT_DIR = SOS_DIR / "images"
LOG_FILE = SOS_DIR / "download.log"
COMPLETE_FLAG = SOS_DIR / "DOWNLOAD_COMPLETE.txt"

URL = "https://zenodo.org/api/records/15298010/files/images.zip/content"
EXPECTED_SIZE = 1148063776  # 1.14 GB
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
}

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def download_resumable():
    SOS_DIR.mkdir(parents=True, exist_ok=True)
    
    while True:
        current_size = TARGET_FILE.stat().st_size if TARGET_FILE.exists() else 0
        if current_size >= EXPECTED_SIZE:
            log(f"[✓] Download already reached complete size: {current_size:,} bytes")
            break
            
        req_headers = dict(HEADERS)
        if current_size > 0:
            req_headers["Range"] = f"bytes={current_size}-"
            log(f"[*] Resuming download from byte {current_size:,} / {EXPECTED_SIZE:,} ({current_size/EXPECTED_SIZE*100:.1f}%)")
        else:
            log(f"[*] Starting download from byte 0 / {EXPECTED_SIZE:,}")
            
        try:
            with requests.get(URL, headers=req_headers, stream=True, timeout=(15, 60)) as r:
                if r.status_code not in (200, 206):
                    log(f"[!] Server returned status {r.status_code}: {r.text[:200]}. Retrying in 5s...")
                    time.sleep(5)
                    continue
                    
                mode = "ab" if current_size > 0 and r.status_code == 206 else "wb"
                if mode == "wb" and current_size > 0:
                    log("[!] Server returned 200 instead of 206; restarting from 0")
                    
                last_log_time = time.time()
                last_log_size = current_size
                
                with open(TARGET_FILE, mode) as f:
                    for chunk in r.iter_content(chunk_size=512 * 1024):  # 512 KB chunks
                        if chunk:
                            f.write(chunk)
                            current_size += len(chunk)
                            now = time.time()
                            if now - last_log_time >= 15:
                                speed_kb = (current_size - last_log_size) / (now - last_log_time) / 1024
                                pct = (current_size / EXPECTED_SIZE) * 100
                                rem_mb = (EXPECTED_SIZE - current_size) / (1024 * 1024)
                                eta_min = (rem_mb * 1024 / speed_kb / 60) if speed_kb > 0 else 0
                                log(f"Progress: {current_size/(1024*1024):.1f} MB / {EXPECTED_SIZE/(1024*1024):.1f} MB ({pct:.1f}%) | Speed: {speed_kb:.0f} KB/s | ETA: {eta_min:.1f} min")
                                last_log_time = now
                                last_log_size = current_size
                                
            # Check if complete
            if TARGET_FILE.exists() and TARGET_FILE.stat().st_size >= EXPECTED_SIZE:
                log(f"[✓] Successfully downloaded all {EXPECTED_SIZE:,} bytes!")
                break
                
        except (requests.exceptions.RequestException, Exception) as e:
            curr = TARGET_FILE.stat().st_size if TARGET_FILE.exists() else 0
            log(f"[!] Connection interrupted ({type(e).__name__}: {e}). Saved {curr/(1024*1024):.1f} MB. Resuming in 3 seconds...")
            time.sleep(3)

def extract_and_verify():
    log("[*] Testing ZIP archive integrity...")
    try:
        with zipfile.ZipFile(TARGET_FILE, "r") as z:
            bad_file = z.testzip()
            if bad_file:
                log(f"[!] Corrupt file detected inside archive: {bad_file}")
                return False
            log("[✓] ZIP archive integrity verified. No corrupted files.")
            
            log(f"[*] Extracting images into {EXTRACT_DIR}...")
            EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
            z.extractall(SOS_DIR)
            log(f"[✓] Extraction complete into {SOS_DIR}")
    except Exception as e:
        log(f"[!] Extraction error: {e}")
        return False
        
    # Count images
    train_imgs = list((SOS_DIR / "images" / "train").glob("*.png")) + list((SOS_DIR / "images" / "train").glob("*.jpg"))
    val_imgs = list((SOS_DIR / "images" / "val").glob("*.png")) + list((SOS_DIR / "images" / "val").glob("*.jpg"))
    log(f"[✓] Verified extracted images: {len(train_imgs):,} train images, {len(val_imgs):,} val images")
    
    with open(COMPLETE_FLAG, "w") as f:
        f.write(f"DOWNLOAD AND EXTRACTION COMPLETE\n")
        f.write(f"Size: {TARGET_FILE.stat().st_size} bytes\n")
        f.write(f"Train images: {len(train_imgs)}\n")
        f.write(f"Val images: {len(val_imgs)}\n")
        f.write(f"Completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    log("[✓] All done! Created DOWNLOAD_COMPLETE.txt")
    return True

if __name__ == "__main__":
    download_resumable()
    extract_and_verify()
