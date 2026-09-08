"""Native HTTP client for the FPGA LAB platform API (contract in captures/api_contract.json).

All methods return parsed JSON (dict). Errors raise PlatformError with platform message.
Single-threaded usage expected per instance (an asyncio server should guard calls).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

BASE_URL = "http://www.logicmatrixsemi.com:5174"
DEFAULT_SESSION_FILE = Path(__file__).resolve().parents[1] / "sessions" / "platform_session.json"


class PlatformError(RuntimeError):
    def __init__(self, message: str, status: int = 0, detail: dict | None = None):
        super().__init__(message)
        self.status = status
        self.detail = detail or {}


class PlatformClient:
    def __init__(self, base_url: str = BASE_URL, session_file: Path = DEFAULT_SESSION_FILE):
        self.base_url = base_url.rstrip("/")
        self.session_file = session_file
        self._client = httpx.Client(base_url=self.base_url, timeout=60.0)
        self.token: str | None = None
        self.refresh_token: str | None = None
        self.expires_at: float | None = None  # epoch seconds, best-effort from JWT exp
        self.user: dict | None = None
        self._load_session()

    # ---------------- auth / session persistence --------------------------
    def _load_session(self):
        if self.session_file and self.session_file.exists():
            try:
                st = json.loads(self.session_file.read_text(encoding="utf-8"))
                self.token = st.get("token")
                self.refresh_token = st.get("refreshToken")
                self.expires_at = st.get("expires_at")
                self.user = st.get("user")
            except Exception:
                pass

    def _save_session(self):
        if self.session_file:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            self.session_file.write_text(json.dumps({
                "token": self.token, "refreshToken": self.refresh_token,
                "expires_at": self.expires_at, "user": self.user,
            }, ensure_ascii=False, indent=1), encoding="utf-8")

    def _auth(self) -> dict[str, str]:
        if not self.token:
            raise PlatformError("not authenticated; call login() first", status=401)
        return {"Authorization": f"Bearer {self.token}"}

    def _request(self, method: str, path: str, *, retry_auth: bool = True, **kw) -> dict:
        resp = self._client.request(method, "/api" + path, headers=self._auth(), **kw)
        j = self._json(resp)
        if resp.status_code == 401 and retry_auth:
            self._refresh()
            resp = self._client.request(method, "/api" + path, headers=self._auth(), **kw)
            j = self._json(resp)
        if resp.status_code >= 400 or j.get("success") is False:
            raise PlatformError(
                j.get("message") or f"platform error status {resp.status_code}",
                status=resp.status_code, detail=j)
        return j

    @staticmethod
    def _json(resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except Exception:
            return {"success": resp.status_code < 400, "message": resp.text[:200],
                    "status_code": resp.status_code}

    # ---------------- login / heartbeat ------------------------------------
    def login(self, identifier: str, password: str, role: str = "developer"):
        r = self._client.post("/api/auth/login", json={
            "identifier": identifier, "password": password, "role": role, "loginType": "local"})
        j = self._json(r)
        if r.status_code != 200 or j.get("success") is not True:
            raise PlatformError(j.get("message") or f"login failed {r.status_code}",
                                status=r.status_code, detail=j)
        d = j["data"]
        self.token = d["token"]
        self.refresh_token = d.get("refreshToken")
        self.user = d.get("user")
        self.expires_at = self._jwt_exp(self.token)
        self._save_session()
        return self.user

    def _refresh(self):
        if not self.refresh_token:
            raise PlatformError("session expired and no refresh token", status=401)
        r = self._client.post("/api/auth/refresh-token", json={"refreshToken": self.refresh_token})
        j = self._json(r)
        if r.status_code != 200 or j.get("success") is not True:
            self.token = None
            raise PlatformError("refresh-token failed; re-login required", status=401, detail=j)
        d = j["data"] if isinstance(j.get("data"), dict) else j
        self.token = d.get("token") or d.get("accessToken") or self.token
        self.refresh_token = d.get("refreshToken") or self.refresh_token
        self.expires_at = self._jwt_exp(self.token)
        self._save_session()

    def relogin_from_account(self, account_file: Path):
        creds = [ln.strip() for ln in account_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.login(creds[0], creds[1])

    @staticmethod
    def _jwt_exp(token: str) -> float | None:
        import base64
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
            return float(exp)
        except Exception:
            return None

    def is_authenticated(self) -> bool:
        if not self.token:
            return False
        if self.expires_at and time.time() >= self.expires_at - 30:
            try:
                self._refresh()
            except Exception:
                return False
        try:
            self._request("GET", "/auth/profile")
            return True
        except Exception:
            return False

    # ---------------- devices / reservation ---------------------------------
    def current_device(self) -> dict | None:
        j = self._request("POST", "/developer/devices/current")
        return j.get("data")

    def device_catalog(self) -> list[dict]:
        j = self._request("POST", "/developer/devices")
        return j.get("data") or []

    def reserve(self, minutes: int = 10, card_type: str = "with_camera") -> dict:
        j = self._request("POST", "/developer/devices/request-by-type",
                          json={"cardType": card_type, "durationMinutes": minutes})
        return j.get("data") or {}

    def release(self, device_id: int):
        self._request("POST", "/developer/devices/release", json={"deviceId": device_id})

    def release_current(self) -> bool:
        cur = self.current_device()
        if cur and cur.get("device_id"):
            self.release(cur["device_id"])
            return True
        return False

    # ---------------- firmware -----------------------------------------------
    def firmware_info(self, device_id: int) -> dict:
        return self._request("GET", f"/modules/firmware/info/{device_id}")

    def firmware_check_jtag(self, device_id: int) -> dict:
        return self._request("POST", "/modules/firmware/check-jtag", json={"deviceId": device_id})

    def firmware_download(self, device_id: int, sbit_path: Path) -> dict:
        sbit_path = Path(sbit_path)
        with sbit_path.open("rb") as f:
            resp = self._client.post(
                "/api/modules/firmware/download", headers=self._auth(),
                data={"deviceId": str(device_id)},
                files={"firmware": (sbit_path.name, f, "application/octet-stream")})
        j = self._json(resp)
        if resp.status_code >= 400 or j.get("success") is not True:
            raise PlatformError(j.get("message") or "download failed", status=resp.status_code, detail=j)
        return j.get("data") or {}

    def firmware_progress(self, device_id: int) -> dict:
        j = self._request("POST", "/modules/firmware/progress", json={"deviceId": device_id})
        return j.get("data") or {}

    def burn_and_wait(self, device_id: int, sbit_path: Path, timeout_s: float = 180.0,
                      poll: float = 1.0) -> dict:
        """Download + poll progress until complete. Returns final progress data."""
        out = self.firmware_download(device_id, sbit_path)
        t0 = time.time()
        last = {}
        while time.time() - t0 < timeout_s:
            time.sleep(poll)
            try:
                last = self.firmware_progress(device_id)
            except Exception:
                continue
            phase = last.get("phase") or last.get("state") or ""
            pct = last.get("percentage")
            if (last.get("isComplete") is True or phase == "complete" or pct == 100):
                return last
            if phase in {"failed", "error"} or last.get("isFailed"):
                raise PlatformError(f"burn failed: {last}")
        raise PlatformError(f"burn timeout; last progress {last}")

    # ---------------- serial ---------------------------------------------------
    def serial_open(self, device_id: int, baud: int = 115200, data_bits: int = 8,
                    stop_bits: int = 1, parity: str = "none", flow_control: int = 0) -> dict:
        return self._request("POST", "/modules/serial-port/open", json={
            "deviceId": device_id, "baudRate": baud, "dataBits": data_bits,
            "stopBits": stop_bits, "parity": parity, "flowControl": flow_control})

    def serial_send(self, device_id: int, data: str, mode: str = "text") -> dict:
        return self._request("POST", "/modules/serial-port/send",
                             json={"deviceId": device_id, "data": data, "mode": mode})

    def serial_read(self, device_id: int, length: int = 64) -> dict:
        return self._request("POST", "/modules/serial-port/read",
                             json={"deviceId": device_id, "length": length})

    def serial_close(self, device_id: int) -> dict:
        return self._request("POST", "/modules/serial-port/close", json={"deviceId": device_id})

    def close(self):
        self._client.close()
