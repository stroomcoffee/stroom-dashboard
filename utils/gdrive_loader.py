# utils/gdrive_loader.py
import os
import time
import requests
import streamlit as st

DB_PATH    = "stroom_inventory.duckdb"
CACHE_SECS = 1800  # re-download setiap 30 menit


def _download_from_gdrive(file_id: str, dest: str) -> bool:
    """Download file dari Google Drive public link."""
    session = requests.Session()

    # Step 1 — coba direct download
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    resp = session.get(url, stream=True, timeout=60)

    # Step 2 — kalau Google minta konfirmasi virus scan, ikuti
    if "text/html" in resp.headers.get("Content-Type", ""):
        # Ambil confirm token
        for key, val in resp.cookies.items():
            if key.startswith("download_warning"):
                url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={val}"
                resp = session.get(url, stream=True, timeout=60)
                break

    if resp.status_code != 200:
        return False

    # Tulis file
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=32768):
            if chunk:
                f.write(chunk)

    os.replace(tmp, dest)
    return True


def ensure_db() -> str:
    """
    Pastikan file DB tersedia secara lokal.
    Download dari GDrive jika:
      - belum ada, atau
      - sudah lebih dari CACHE_SECS detik sejak terakhir download
    Kembalikan path ke file DB.
    """
    file_id = st.secrets.get("GDRIVE_FILE_ID", "")

    # Mode lokal (tidak ada secret) — gunakan DB yang sudah ada
    if not file_id:
        return DB_PATH

    need_download = (
        not os.path.exists(DB_PATH)
        or (time.time() - os.path.getmtime(DB_PATH)) > CACHE_SECS
    )

    if need_download:
        with st.spinner("🔄 Mengambil database terbaru dari Google Drive..."):
            ok = _download_from_gdrive(file_id, DB_PATH)
            if not ok:
                st.warning("⚠️ Gagal download DB dari GDrive, menggunakan data lokal terakhir.")

    return DB_PATH
