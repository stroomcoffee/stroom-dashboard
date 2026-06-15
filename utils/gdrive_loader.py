# utils/gdrive_loader.py
import os
import time
import json
import requests
import streamlit as st

DB_PATH    = "stroom_inventory.duckdb"
CACHE_SECS = 1800  # re-download setiap 30 menit


def _get_access_token() -> str:
    """Dapatkan OAuth2 access token dari service account credentials."""
    import jwt  # PyJWT
    creds = st.secrets["gcp_service_account"]
    now = int(time.time())
    payload = {
        "iss": creds["client_email"],
        "scope": "https://www.googleapis.com/auth/drive",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }
    private_key = creds["private_key"]
    token = jwt.encode(payload, private_key, algorithm="RS256")
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": token,
    })
    return resp.json()["access_token"]


def _download_from_gdrive(file_id: str, dest: str) -> bool:
    """Download file dari Google Drive menggunakan service account."""
    try:
        access_token = _get_access_token()
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            stream=True,
            timeout=120
        )
        if resp.status_code != 200:
            return False
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=32768):
                if chunk:
                    f.write(chunk)
        os.replace(tmp, dest)
        return True
    except Exception as e:
        st.warning(f"Download error: {e}")
        return False


def upload_to_gdrive() -> bool:
    """
    Upload file .duckdb yang sudah terupdate ke Google Drive.
    Dipanggil setelah setiap import CSV berhasil.
    """
    file_id = st.secrets.get("GDRIVE_FILE_ID", "")
    if not file_id:
        return False
    if not os.path.exists(DB_PATH):
        return False

    try:
        access_token = _get_access_token()
        url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media"
        with open(DB_PATH, "rb") as f:
            resp = requests.patch(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/octet-stream",
                },
                data=f,
                timeout=300
            )
        return resp.status_code == 200
    except Exception as e:
        st.warning(f"Upload error: {e}")
        return False


def ensure_db() -> str:
    """
    Pastikan file DB tersedia secara lokal.
    Download dari GDrive jika belum ada atau sudah lebih dari CACHE_SECS.
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
