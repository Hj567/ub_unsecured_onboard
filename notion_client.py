import io
import mimetypes
import requests

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionError(Exception):
    pass


class NotionClient:
    """
    Minimal Notion client for:
      - creating pages
      - updating page properties
      - reading a page
      - direct file uploads (single_part) and attaching to 'files' properties
      - building property payloads from our schema field defs
    """

    def __init__(self, token: str, database_id: str):
        self.token = token
        self.database_id = database_id

        # JSON requests
        self.headers_json = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        # Multipart uploads: DO NOT set Content-Type (requests sets boundary)
        self.headers_upload = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
        }

    # ---------------------------------------------------------------------
    # File uploads (single_part)
    # ---------------------------------------------------------------------
    def _create_file_upload(self, filename: str) -> str:
        """
        Create a new File Upload object in Notion.
        Notion infers the 'original content type' from the filename.
        """
        r = requests.post(
            f"{NOTION_API}/file_uploads",
            headers=self.headers_json,
            json={"filename": filename, "mode": "single_part"},
            timeout=30,
        )
        if r.status_code >= 300:
            raise NotionError(f"Create file upload failed: {r.status_code} {r.text}")
        data = r.json()
        return data["id"]

    def _send_file_upload(
        self,
        upload_id: str,
        filename: str,
        fileobj,
        content_type: str | None = None,
    ) -> None:
        """
        Send the bytes for the previously created File Upload.
        IMPORTANT: content_type should match what Notion inferred from filename
        (e.g., application/pdf for .pdf). If mismatched, Notion returns 400.
        """
        ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        r = requests.post(
            f"{NOTION_API}/file_uploads/{upload_id}/send",
            headers=self.headers_upload,
            files={"file": (filename, fileobj, ct)},
            timeout=180,
        )
        if r.status_code >= 300:
            raise NotionError(f"Send file upload failed: {r.status_code} {r.text}")

    def upload_and_get_id(self, filename: str, fileobj) -> str:
        """
        Upload from a file-like object. Returns the upload id to use in a 'files' property.
        """
        upload_id = self._create_file_upload(filename)
        try:
            fileobj.seek(0)
        except Exception:
            pass
        ct = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self._send_file_upload(upload_id, filename, fileobj, content_type=ct)
        return upload_id

    def upload_bytes_and_get_id(self, filename: str, file_bytes: bytes, content_type: str | None = None) -> str:
        """
        Upload from raw bytes. Returns the upload id to use in a 'files' property.
        """
        upload_id = self._create_file_upload(filename)
        ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        self._send_file_upload(upload_id, filename, io.BytesIO(file_bytes), content_type=ct)
        return upload_id

    # ---------------------------------------------------------------------
    # Pages
    # ---------------------------------------------------------------------
    def create_page(self, properties: dict) -> dict:
        payload = {"parent": {"database_id": self.database_id}, "properties": properties}
        r = requests.post(f"{NOTION_API}/pages", headers=self.headers_json, json=payload, timeout=30)
        if r.status_code >= 300:
            raise NotionError(f"Notion error: {r.status_code} {r.text}")
        return r.json()

    def update_page_properties(self, page_id: str, prop_update: dict) -> dict:
        r = requests.patch(
            f"{NOTION_API}/pages/{page_id}",
            headers=self.headers_json,
            json={"properties": prop_update},
            timeout=30,
        )
        if r.status_code >= 300:
            raise NotionError(f"Update page failed: {r.status_code} {r.text}")
        return r.json()

    def get_page(self, page_id: str) -> dict:
        r = requests.get(f"{NOTION_API}/pages/{page_id}", headers=self.headers_json, timeout=30)
        if r.status_code >= 300:
            raise NotionError(f"Get page failed: {r.status_code} {r.text}")
        return r.json()

    # ---------------------------------------------------------------------
    # Property builder (maps our schema field defs to Notion payloads)
    # ---------------------------------------------------------------------
    def build_property(self, fdef: dict, value):
        """
        fdef: {
          "name": "Label for UI",
          "type": "title|rich_text|number|date|select|multi_select|checkbox|url|email|phone|status|files|relation",
          "notion_prop": "Exact Notion property name",
          ... (format/options/etc.)
        }
        value: cleaned form value (string, list, bool, files, etc.)
        """
        t = fdef["type"]
        prop_name = fdef["notion_prop"]

        # Empty values for most types (checkbox/files handled explicitly)
        if value in (None, "", []) and t not in ("checkbox", "files"):
            if t == "title":       return prop_name, {"title": []}
            if t == "rich_text":   return prop_name, {"rich_text": []}
            if t == "number":      return prop_name, {"number": None}
            if t == "date":        return prop_name, {"date": None}
            if t == "select":      return prop_name, {"select": None}
            if t == "multi_select":return prop_name, {"multi_select": []}
            if t == "url":         return prop_name, {"url": None}
            if t == "email":       return prop_name, {"email": None}
            if t == "phone":       return prop_name, {"phone_number": None}
            if t == "status":      return prop_name, {"status": None}
            if t == "relation":    return prop_name, {"relation": []}

        # Populated
        if t == "title":
            return prop_name, {"title": [{"type": "text", "text": {"content": value}}]}
        if t == "rich_text":
            return prop_name, {"rich_text": [{"type": "text", "text": {"content": value}}]}
        if t == "number":
            num = int(value) if fdef.get("format") == "int" else float(value)
            return prop_name, {"number": num}
        if t == "date":
            return prop_name, {"date": {"start": value}}
        if t == "select":
            return prop_name, {"select": {"name": value}}
        if t == "multi_select":
            return prop_name, {"multi_select": [{"name": v} for v in value]}
        if t == "checkbox":
            return prop_name, {"checkbox": (value == "on" or value is True)}
        if t == "url":
            return prop_name, {"url": value}
        if t == "email":
            return prop_name, {"email": value}
        if t == "phone":
            return prop_name, {"phone_number": value}
        if t == "status":
            return prop_name, {"status": {"name": value}}
        if t == "relation":
            # Expect list of page IDs
            return prop_name, {"relation": [{"id": rid} for rid in (value or [])]}
        if t == "files":
            files_payload = []
            for fs in (value or []):
                if not fs or not getattr(fs, "filename", ""):
                    continue
                token = self.upload_and_get_id(fs.filename, fs)  # MIME auto-guessed from filename
                files_payload.append({
                    "name": fs.filename,
                    "type": "file_upload",
                    "file_upload": {"id": token},
                })
            return prop_name, {"files": files_payload}

        raise NotionError(f"Unsupported field type: {t}")
