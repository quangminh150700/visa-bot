"""
VFS Global Appointment Checker
Gọi trực tiếp API của VFS Global để kiểm tra lịch trống.
"""
import asyncio
import logging
import httpx
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Mapping mã quốc gia → tên hiển thị
COUNTRY_NAMES = {
    "vnm": "Việt Nam",
    "fra": "Pháp",
    "deu": "Đức",
    "ita": "Ý",
    "esp": "Tây Ban Nha",
    "nld": "Hà Lan",
    "bel": "Bỉ",
    "che": "Thụy Sĩ",
    "aut": "Áo",
    "prt": "Bồ Đào Nha",
    "grc": "Hy Lạp",
    "dnk": "Đan Mạch",
    "swe": "Thụy Điển",
    "fin": "Phần Lan",
    "nor": "Na Uy",
    "pol": "Ba Lan",
    "hrv": "Croatia",
    "lux": "Luxembourg",
    "mlt": "Malta",
}


class VFSChecker:
    BASE_API = "https://lift.vfsglobal.com/prod/api/v1"

    def __init__(
        self,
        username: str,
        password: str,
        origin_country: str,   # Ví dụ: "vnm"
        target_country: str,   # Ví dụ: "fra"
        visa_category: str = "Tourist",
        visa_subcategory: str = "Tourist Visa",
    ):
        self.username = username
        self.password = password
        self.origin = origin_country.lower()
        self.target = target_country.lower()
        self.visa_category = visa_category
        self.visa_subcategory = visa_subcategory
        self.token: Optional[str] = None

        self.portal_url = f"https://visa.vfsglobal.com/{self.origin}/en/{self.target}"

    def _default_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Referer": self.portal_url + "/",
            "Origin": "https://visa.vfsglobal.com",
        }

    async def _login(self, client: httpx.AsyncClient) -> str:
        """Đăng nhập VFS Global, trả về Bearer token."""
        payload = {
            "username": self.username,
            "password": self.password,
            "grant_type": "password",
            "country": f"vfsglobal-{self.target}",
            "origin": self.origin,
            "brandName": "vfsglobal",
            "lang": "en-US",
        }
        headers = {**self._default_headers(), "Content-Type": "application/json"}
        resp = await client.post(
            f"{self.BASE_API}/user/login",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("token") or data.get("access_token")
        if not token:
            raise ValueError(f"Không lấy được token. Response: {data}")
        logger.info("Đăng nhập VFS Global thành công.")
        return token

    async def _get_centers(self, client: httpx.AsyncClient) -> List[Dict]:
        """Lấy danh sách trung tâm và slot trống."""
        headers = {
            **self._default_headers(),
            "Authorization": f"Bearer {self.token}",
        }
        params = {
            "country": f"vfsglobal-{self.target}",
            "language": "en-US",
            "origin": self.origin,
            "category": self.visa_category,
            "subcategory": self.visa_subcategory,
            "count": "1",
        }
        resp = await client.get(
            f"{self.BASE_API}/appointment/checkslots",
            params=params,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def _get_earliest_dates(self, client: httpx.AsyncClient, center_name: str) -> List[str]:
        """Lấy ngày sớm nhất khả dụng tại một trung tâm."""
        headers = {
            **self._default_headers(),
            "Authorization": f"Bearer {self.token}",
        }
        params = {
            "country": f"vfsglobal-{self.target}",
            "language": "en-US",
            "origin": self.origin,
            "category": self.visa_category,
            "subcategory": self.visa_subcategory,
            "center": center_name,
            "count": "10",
        }
        try:
            resp = await client.get(
                f"{self.BASE_API}/appointment/slots/checkavailability",
                params=params,
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return [str(d) for d in data if d]
                if isinstance(data, dict) and "dates" in data:
                    return data["dates"]
        except Exception as e:
            logger.warning(f"Không lấy được ngày cụ thể cho {center_name}: {e}")
        return []

    async def check_available_slots(self) -> List[Dict]:
        """
        Kiểm tra slot khả dụng trên VFS Global.
        Trả về danh sách dict: [{"center": ..., "earliest_date": ..., "slots": [...]}]
        """
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            try:
                self.token = await self._login(client)
            except httpx.HTTPStatusError as e:
                raise ConnectionError(
                    f"Đăng nhập thất bại (HTTP {e.response.status_code}): "
                    "Kiểm tra lại VFS_USERNAME / VFS_PASSWORD"
                )

            try:
                raw = await self._get_centers(client)
            except httpx.HTTPStatusError as e:
                raise ConnectionError(f"Lỗi khi kiểm tra slot: HTTP {e.response.status_code}")

            available = []

            # raw có thể là list trung tâm hoặc dict
            centers = raw if isinstance(raw, list) else [raw]

            for center in centers:
                if not isinstance(center, dict):
                    continue

                # Có thể tên field khác nhau tuỳ version API
                name = (
                    center.get("centerName")
                    or center.get("name")
                    or center.get("locationName")
                    or "Không rõ"
                )
                slots = (
                    center.get("slots")
                    or center.get("availableSlots")
                    or []
                )
                earliest = (
                    center.get("earliestDate")
                    or center.get("firstAvailableDate")
                    or ""
                )

                # Nếu có slot hoặc có earliest date thì báo
                if slots or earliest:
                    dates = await self._get_earliest_dates(client, name)
                    available.append({
                        "center": name,
                        "earliest_date": earliest or (dates[0] if dates else ""),
                        "slots": dates or slots,
                        "booking_url": self.portal_url,
                    })

            return available

    @property
    def origin_name(self) -> str:
        return COUNTRY_NAMES.get(self.origin, self.origin.upper())

    @property
    def target_name(self) -> str:
        return COUNTRY_NAMES.get(self.target, self.target.upper())
