import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import httpx

log = logging.getLogger("vyom.cloud_storage")

class BaseStorageProvider(ABC):
    """Abstract base class for cloud storage providers (e.g. Google Drive, OneDrive, Dropbox)."""

    @abstractmethod
    def get_auth_url(self, email: str, redirect_uri: str) -> str:
        """Get the OAuth authorization URL for this provider."""
        pass

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Exchange the OAuth authorization code for credentials (tokens)."""
        pass

    @abstractmethod
    async def refresh_credentials(self, credentials: dict) -> dict:
        """Refresh the OAuth credentials if expired."""
        pass

    @abstractmethod
    async def upload_file(
        self, filename: str, content: bytes, folder_path: List[str], credentials: dict
    ) -> dict:
        """Upload a file to the provider inside the specified folder path.
        Returns a dict containing file_id, view_url, and the (potentially updated) credentials."""
        pass

    @abstractmethod
    async def get_about_info(self, credentials: dict) -> dict:
        """Get information about the user's storage limits and usage.
        Returns a dict containing limit, usage, and potentially updated credentials."""
        pass


class GoogleDriveProvider(BaseStorageProvider):
    """Google Drive cloud storage provider using direct HTTP REST API calls."""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    def get_auth_url(self, email: str, redirect_uri: str) -> str:
        import urllib.parse
        scopes = [
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/userinfo.email"
        ]
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": email,
            "access_type": "offline",
            "prompt": "consent"
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, data=data)
            if resp.status_code != 200:
                log.error("Google OAuth token exchange failed: %s", resp.text)
                raise RuntimeError(f"Failed to exchange Google OAuth code: {resp.text}")
            token_data = resp.json()
            
            # Fetch connected Google user email
            access_token = token_data.get("access_token")
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            google_email = None
            try:
                userinfo_resp = await client.get(userinfo_url, headers={"Authorization": f"Bearer {access_token}"})
                if userinfo_resp.status_code == 200:
                    google_email = userinfo_resp.json().get("email")
            except Exception as e:
                log.warning("Could not fetch Google user info: %s", e)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": time.time() + token_data.get("expires_in", 3600),
                "google_email": google_email,
                "connected_at": time.time()
            }

    async def refresh_credentials(self, credentials: dict) -> dict:
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise ValueError("No refresh token available to renew credentials")
            
        url = "https://oauth2.googleapis.com/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, data=data)
            if resp.status_code != 200:
                log.error("Google OAuth refresh failed: %s", resp.text)
                raise RuntimeError(f"Failed to refresh Google OAuth token: {resp.text}")
            token_data = resp.json()
            
            credentials["access_token"] = token_data["access_token"]
            credentials["expires_at"] = time.time() + token_data.get("expires_in", 3600)
            log.info("Successfully refreshed Google Drive access token")
            return credentials

    async def upload_file(
        self, filename: str, content: bytes, folder_path: List[str], credentials: dict
    ) -> dict:
        # Check expiration (with 60 seconds clock skew tolerance)
        if credentials.get("expires_at", 0) - 60 < time.time():
            credentials = await self.refresh_credentials(credentials)
            
        token = credentials.get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient(timeout=45.0) as client:
            # 1. Resolve folder path recursively
            parent_id = "root"
            for folder_name in folder_path:
                query = (
                    f"name = '{folder_name}' and "
                    "mimeType = 'application/vnd.google-apps.folder' and "
                    f"'{parent_id}' in parents and "
                    "trashed = false"
                )
                q_resp = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers=headers,
                    params={"q": query, "fields": "files(id)"}
                )
                if q_resp.status_code != 200:
                    raise RuntimeError(f"Failed to query Google Drive folder '{folder_name}': {q_resp.text}")
                
                files = q_resp.json().get("files", [])
                if files:
                    parent_id = files[0]["id"]
                else:
                    # Create folder
                    meta = {
                        "name": folder_name,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [parent_id]
                    }
                    create_resp = await client.post(
                        "https://www.googleapis.com/drive/v3/files",
                        headers=headers,
                        json=meta
                    )
                    if create_resp.status_code != 200:
                        raise RuntimeError(f"Failed to create Google Drive folder '{folder_name}': {create_resp.text}")
                    parent_id = create_resp.json()["id"]

            # 2. Check if a report file with the exact name already exists in target folder to update/overwrite it
            query = f"name = '{filename}' and '{parent_id}' in parents and trashed = false"
            q_file_resp = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                params={"q": query, "fields": "files(id)"}
            )
            file_id = None
            if q_file_resp.status_code == 200:
                files = q_file_resp.json().get("files", [])
                if files:
                    file_id = files[0]["id"]

            if file_id:
                # Update existing file content
                upload_url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media"
                up_resp = await client.patch(
                    upload_url,
                    headers={**headers, "Content-Type": "application/pdf"},
                    content=content
                )
                if up_resp.status_code != 200:
                    raise RuntimeError(f"Failed to update Google Drive file content: {up_resp.text}")
            else:
                # Create new file metadata
                meta = {
                    "name": filename,
                    "mimeType": "application/pdf",
                    "parents": [parent_id]
                }
                create_file_resp = await client.post(
                    "https://www.googleapis.com/drive/v3/files",
                    headers=headers,
                    json=meta
                )
                if create_file_resp.status_code != 200:
                    raise RuntimeError(f"Failed to create Google Drive file metadata: {create_file_resp.text}")
                file_id = create_file_resp.json()["id"]
                
                # Upload content
                upload_url = f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media"
                up_resp = await client.patch(
                    upload_url,
                    headers={**headers, "Content-Type": "application/pdf"},
                    content=content
                )
                if up_resp.status_code != 200:
                    raise RuntimeError(f"Failed to upload Google Drive file content: {up_resp.text}")

            # 3. Fetch webViewLink (view URL)
            info_resp = await client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                headers=headers,
                params={"fields": "id, name, webViewLink"}
            )
            if info_resp.status_code != 200:
                raise RuntimeError(f"Failed to retrieve Google Drive file info: {info_resp.text}")
                
            info = info_resp.json()
            return {
                "file_id": file_id,
                "view_url": info.get("webViewLink"),
                "credentials": credentials
            }

    async def get_about_info(self, credentials: dict) -> dict:
        # Check expiration (with 60 seconds clock skew tolerance)
        if credentials.get("expires_at", 0) - 60 < time.time():
            credentials = await self.refresh_credentials(credentials)
            
        token = credentials.get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://www.googleapis.com/drive/v3/about",
                headers=headers,
                params={"fields": "storageQuota"}
            )
            if resp.status_code == 200:
                quota = resp.json().get("storageQuota", {})
                return {
                    "limit": int(quota.get("limit", 15 * 1024 * 1024 * 1024)),
                    "usage": int(quota.get("usage", 0)),
                    "credentials": credentials
                }
            else:
                log.error("Failed to fetch Google Drive about info: %s", resp.text)
                raise RuntimeError(f"Failed to fetch Google Drive about info: {resp.text}")


class MockGoogleDriveProvider(BaseStorageProvider):
    """Mock Google Drive provider for testing when credentials are not configured in environment."""

    def __init__(self):
        self.client_id = "mock-client-id"
        self.client_secret = "mock-client-secret"

    def get_auth_url(self, email: str, redirect_uri: str) -> str:
        import urllib.parse
        params = {
            "code": "mock-auth-code",
            "state": email
        }
        # Direct redirect back to callback uri for seamless instant authentication in mock mode
        return redirect_uri + ("&" if "?" in redirect_uri else "?") + urllib.parse.urlencode(params)

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        return {
            "access_token": "mock-access-token",
            "refresh_token": "mock-refresh-token",
            "expires_at": time.time() + 3600,
            "google_email": "demo-teacher@classmind.com"
        }

    async def refresh_credentials(self, credentials: dict) -> dict:
        credentials["access_token"] = "mock-refreshed-access-token"
        credentials["expires_at"] = time.time() + 3600
        return credentials

    async def upload_file(
        self, filename: str, content: bytes, folder_path: List[str], credentials: dict
    ) -> dict:
        import uuid
        file_id = f"mock-file-id-{uuid.uuid4()}"
        view_url = f"https://drive.google.com/open?id={file_id}"
        return {
            "file_id": file_id,
            "view_url": view_url,
            "credentials": credentials
        }

    async def get_about_info(self, credentials: dict) -> dict:
        return {
            "limit": 15 * 1024 * 1024 * 1024,
            "usage": int(2.4 * 1024 * 1024 * 1024),
            "credentials": credentials
        }
