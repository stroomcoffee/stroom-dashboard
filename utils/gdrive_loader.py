# utils/gdrive_loader.py
import os
import time
import json
import base64
import hmac
import hashlib
import requests
import streamlit as st

DB_PATH    = "stroom_inventory.duckdb"
CACHE_SECS = 1800  # re-download setiap 30 menit


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _get_access_token() -> str:
    """Dapatkan OAuth2 access token dari service account — tanpa PyJWT."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend

    creds = st.secrets["gcp_service_account"]
    now = int(time.time())

    header  = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "iss": creds["client_email"],
        "scope": "https://www.googleapis.com/auth/drive",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }).encode())

    msg = f"{header}.{payload}".encode()

    private_key = serialization.load_pem_private_key(
        creds["private_key"].encode(),
        password=None,
        backend=default_backend()
    )
    signature = private_key.sign(msg, padding.PKCS1v15(), hashes.SHA256())
    jwt_token = f"{header}.{payload}.{_b64url(signature)}"

    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token,
    }, timeout=30)
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
    """Upload .duckdb ke Google Drive setelah import CSV berhasil."""
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
    """Pastikan file DB tersedia secara lokal, download dari GDrive jika perlu."""
    file_id = st.secrets.get("GDRIVE_FILE_ID", "")

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