"""
Telegram Command Handler
Chạy mỗi 5 phút để kiểm tra lệnh mới từ người dùng.

Các lệnh hỗ trợ:
  /france   → Kiểm tra Pháp
  /italy    → Kiểm tra Ý
  /spain    → Kiểm tra Tây Ban Nha
  /portugal → Kiểm tra Bồ Đào Nha
  /all      → Kiểm tra tất cả
  /help     → Danh sách lệnh
"""

import asyncio
import httpx
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from visa_checker import VFSChecker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("telegram_handler")

VN_TZ = timezone(timedelta(hours=7))

# Mapping lệnh → mã nước
COMMAND_MAP = {
    "/france":    "fra",
    "/phap":      "fra",
    "/italy":     "ita",
    "/italia":    "ita",
    "/spain":     "esp",
    "/tbn":       "esp",
    "/portugal":  "prt",
    "/bdn":       "prt",
}

HELP_TEXT = (
    "🤖 <b>Visa Bot — Danh sách lệnh</b>\n\n"
    "/france — Kiểm tra Pháp 🇫🇷\n"
    "/italy — Kiểm tra Ý 🇮🇹\n"
    "/spain — Kiểm tra Tây Ban Nha 🇪🇸\n"
    "/portugal — Kiểm tra Bồ Đào Nha 🇵🇹\n"
    "/all — Kiểm tra tất cả 🌍\n"
    "/help — Danh sách lệnh này\n\n"
    "⏱ <i>Bot phản hồi trong vòng 5 phút.</i>"
)


async def send_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        await client.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        })


async def get_recent_updates(token: str, since_seconds: int = 310) -> list:
    """Lấy tin nhắn trong N giây gần đây (mặc định 5 phút 10 giây)."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    cutoff = time.time() - since_seconds
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"limit": 100, "timeout": 0})
        resp.raise_for_status()
        updates = resp.json().get("result", [])
    return [u for u in updates if u.get("message", {}).get("date", 0) >= cutoff]


async def check_country_and_reply(
    country_code: str,
    config: dict,
    chat_id: str,
) -> None:
    """Kiểm tra một nước và gửi kết quả về Telegram."""
    token = config["telegram_token"]
    checker = VFSChecker(
        username=config["vfs_username"],
        password=config["vfs_password"],
        origin_country=config["origin_country"],
        target_country=country_code,
        visa_category=config["visa_category"],
        visa_subcategory=config["visa_subcategory"],
    )

    await send_message(token, chat_id,
        f"🔍 Đang kiểm tra lịch visa <b>{checker.target_name}</b>..."
    )

    try:
        slots = await checker.check_available_slots()
        now_vn = datetime.now(VN_TZ).strftime("%H:%M %d/%m/%Y")

        if slots:
            lines = [f"✅ <b>Đất nước: {checker.target_name}</b>\n"]
            for slot in slots:
                center   = slot.get("center", "Không rõ")
                earliest = slot.get("earliest_date", "Không rõ")
                url      = slot.get("booking_url", checker.portal_url)
                lines.append(f"📍 Trung tâm: <b>{center}</b>")
                lines.append(f"📅 Ngày trống gần nhất: <b>{earliest}</b>")
                lines.append(f"🔗 <a href='{url}'>Đặt lịch ngay</a>\n")
            lines.append(f"🕐 Kiểm tra lúc: {now_vn}")
            await send_message(token, chat_id, "\n".join(lines))
        else:
            await send_message(token, chat_id,
                f"❌ <b>Đất nước: {checker.target_name}</b>\n"
                f"Chưa có lịch trống.\n"
                f"🕐 Kiểm tra lúc: {now_vn}"
            )

    except Exception as e:
        await send_message(token, chat_id,
            f"⚠️ Lỗi khi kiểm tra <b>{checker.target_name}</b>:\n"
            f"<code>{str(e)[:300]}</code>"
        )


async def main() -> None:
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "VFS_USERNAME", "VFS_PASSWORD"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error(f"Thiếu biến môi trường: {', '.join(missing)}")
        sys.exit(1)

    config = {
        "telegram_token":   os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID"),
        "vfs_username":     os.getenv("VFS_USERNAME"),
        "vfs_password":     os.getenv("VFS_PASSWORD"),
        "origin_country":   os.getenv("ORIGIN_COUNTRY", "vnm"),
        "visa_category":    os.getenv("VISA_CATEGORY", "Tourist"),
        "visa_subcategory": os.getenv("VISA_SUBCATEGORY", "Tourist Visa"),
        "target_countries": [
            c.strip() for c in
            os.getenv("TARGET_COUNTRIES", "fra,ita,esp,prt").split(",")
        ],
    }

    token   = config["telegram_token"]
    chat_id = config["telegram_chat_id"]

    logger.info("Kiểm tra lệnh Telegram mới...")
    updates = await get_recent_updates(token, since_seconds=310)

    if not updates:
        logger.info("Không có lệnh mới trong 5 phút vừa qua.")
        return

    processed = set()

    for update in updates:
        msg     = update.get("message", {})
        text    = msg.get("text", "").strip()
        msg_cid = str(msg.get("chat", {}).get("id", ""))
        update_id = update.get("update_id")

        # Bỏ qua nếu đã xử lý hoặc không phải từ chat đã cấu hình
        if update_id in processed or msg_cid != chat_id:
            continue
        processed.add(update_id)

        # Tách lệnh (bỏ @botname nếu có), chuyển về chữ thường
        raw_cmd = text.split()[0].split("@")[0].lower() if text else ""
        if not raw_cmd.startswith("/"):
            continue

        logger.info(f"Nhận lệnh: {raw_cmd}")

        if raw_cmd == "/help":
            await send_message(token, chat_id, HELP_TEXT)

        elif raw_cmd in ("/all", "/status"):
            countries = config["target_countries"]
            await send_message(token, chat_id,
                f"🌍 Đang kiểm tra <b>{len(countries)} nước</b>...\n"
                "Kết quả sẽ gửi lần lượt."
            )
            for country in countries:
                await check_country_and_reply(country, config, chat_id)
                await asyncio.sleep(2)

        elif raw_cmd in COMMAND_MAP:
            country_code = COMMAND_MAP[raw_cmd]
            await check_country_and_reply(country_code, config, chat_id)

        else:
            await send_message(token, chat_id,
                f"❓ Lệnh <code>{raw_cmd}</code> không hợp lệ.\n"
                "Gõ /help để xem danh sách lệnh."
            )


if __name__ == "__main__":
    asyncio.run(main())
