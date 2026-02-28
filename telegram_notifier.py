"""
Telegram Notifier
Gửi thông báo qua Telegram Bot API.
"""
import httpx
import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    API_BASE = "https://api.telegram.org"

    def __init__(self, token: str, chat_id: str):
        if not token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID không được để trống!")
        self.token = token
        self.chat_id = str(chat_id)

    async def _send(self, text: str, parse_mode: str = "HTML") -> bool:
        """Gửi tin nhắn Telegram."""
        url = f"{self.API_BASE}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("Đã gửi thông báo Telegram thành công.")
                return True
        except Exception as e:
            logger.error(f"Gửi Telegram thất bại: {e}")
            return False

    async def send_startup_message(
        self, origin: str, target: str, interval_minutes: int
    ) -> None:
        """Thông báo bot khởi động."""
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        text = (
            "🤖 <b>Visa Bot đã khởi động!</b>\n\n"
            f"📍 Theo dõi: <b>{origin} → {target}</b> (VFS Global)\n"
            f"⏱ Kiểm tra mỗi: <b>{interval_minutes} phút</b>\n"
            f"🕐 Thời gian: {now}\n\n"
            "✅ Bot sẽ thông báo ngay khi có lịch trống và gửi báo cáo hàng ngày."
        )
        await self._send(text)

    async def send_slots_found(
        self,
        slots: List[Dict],
        origin_name: str,
        target_name: str,
    ) -> None:
        """Thông báo khi tìm thấy lịch trống — ƯU TIÊN CAO."""
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        lines = [
            "🚨 <b>CÓ LỊCH VISA TRỐNG!</b> 🚨\n",
            f"📍 <b>{origin_name} → {target_name}</b> (VFS Global)",
            f"🕐 Phát hiện lúc: {now}\n",
        ]
        for i, slot in enumerate(slots, 1):
            center = slot.get("center", "Không rõ")
            earliest = slot.get("earliest_date", "")
            booking_url = slot.get("booking_url", "https://visa.vfsglobal.com")
            all_slots = slot.get("slots", [])

            lines.append(f"📌 <b>Trung tâm {i}: {center}</b>")
            if earliest:
                lines.append(f"   📅 Ngày sớm nhất: <b>{earliest}</b>")
            if all_slots:
                dates_preview = ", ".join(str(s) for s in all_slots[:5])
                if len(all_slots) > 5:
                    dates_preview += f" ... (+{len(all_slots)-5} ngày khác)"
                lines.append(f"   📋 Các ngày: {dates_preview}")
            lines.append(f"   🔗 <a href='{booking_url}'>Đặt lịch ngay</a>\n")

        lines.append("⚡ <b>Hãy vào đặt lịch ngay trước khi hết!</b>")
        await self._send("\n".join(lines))

    async def send_daily_report(
        self,
        slots: List[Dict],
        origin_name: str,
        target_name: str,
        total_checks: int,
        errors_today: int,
        booking_url: str,
    ) -> None:
        """Báo cáo hàng ngày (gửi lúc 8h sáng)."""
        now = datetime.now().strftime("%d/%m/%Y")
        status_icon = "✅" if slots else "❌"
        status_text = f"{len(slots)} trung tâm có lịch trống" if slots else "Chưa có lịch trống"

        lines = [
            f"📊 <b>Báo cáo ngày {now}</b>\n",
            f"📍 Visa <b>{origin_name} → {target_name}</b>",
            f"{status_icon} Tình trạng: <b>{status_text}</b>",
            f"🔍 Số lần kiểm tra hôm nay: {total_checks}",
        ]
        if errors_today > 0:
            lines.append(f"⚠️ Lỗi gặp phải: {errors_today}")

        if slots:
            lines.append("\n<b>Chi tiết lịch trống:</b>")
            for slot in slots:
                center = slot.get("center", "Không rõ")
                earliest = slot.get("earliest_date", "Không rõ")
                lines.append(f"  • {center}: ngày sớm nhất <b>{earliest}</b>")
            lines.append(f"\n🔗 <a href='{booking_url}'>Đặt lịch tại đây</a>")
        else:
            lines.append(
                "\n💡 <i>Không có lịch trống hôm nay. Bot sẽ tiếp tục theo dõi.</i>"
            )

        await self._send("\n".join(lines))

    async def send_no_slots(
        self, origin_name: str, target_name: str, next_check_minutes: int
    ) -> None:
        """Thông báo khi không có lịch (tùy chọn, tắt theo mặc định)."""
        text = (
            f"🔍 Kiểm tra xong — Chưa có lịch trống\n"
            f"📍 {origin_name} → {target_name}\n"
            f"⏱ Kiểm tra lại sau {next_check_minutes} phút."
        )
        await self._send(text)

    async def send_error(self, error_msg: str, context: str = "") -> None:
        """Thông báo lỗi."""
        ctx = f" ({context})" if context else ""
        text = (
            f"⚠️ <b>Lỗi Bot{ctx}</b>\n\n"
            f"<code>{error_msg[:500]}</code>\n\n"
            "Bot sẽ thử lại ở lần kiểm tra tiếp theo."
        )
        await self._send(text)

    async def send_test(self) -> bool:
        """Gửi tin nhắn test để xác minh cấu hình."""
        text = (
            "✅ <b>Kết nối Telegram thành công!</b>\n\n"
            "Bot đã sẵn sàng theo dõi lịch visa VFS Global.\n"
            "Bạn sẽ nhận thông báo ngay khi có lịch trống."
        )
        return await self._send(text)
