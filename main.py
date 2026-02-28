"""
Visa Bot — GitHub Actions Edition
Chạy MỘT LẦN: kiểm tra slot → gửi Telegram → thoát.
GitHub Actions sẽ tự gọi lại theo lịch (mỗi 30 phút).
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from visa_checker import VFSChecker
from telegram_notifier import TelegramNotifier

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("visa_bot")

# Múi giờ Việt Nam (UTC+7)
VN_TZ = timezone(timedelta(hours=7))


# ─── Config ──────────────────────────────────────────────────────────────────
def get_config() -> dict:
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "VFS_USERNAME", "VFS_PASSWORD"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error(f"❌ Thiếu biến môi trường: {', '.join(missing)}")
        logger.error("   → Vào repo GitHub: Settings → Secrets → New secret")
        sys.exit(1)

    return {
        "telegram_token":    os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id":  os.getenv("TELEGRAM_CHAT_ID"),
        "vfs_username":      os.getenv("VFS_USERNAME"),
        "vfs_password":      os.getenv("VFS_PASSWORD"),
        "origin_country":    os.getenv("ORIGIN_COUNTRY", "vnm"),
        "target_country":    os.getenv("TARGET_COUNTRY", "fra"),
        "visa_category":     os.getenv("VISA_CATEGORY", "Tourist"),
        "visa_subcategory":  os.getenv("VISA_SUBCATEGORY", "Tourist Visa"),
        # Giờ gửi báo cáo ngày theo giờ Việt Nam (0-23)
        "daily_report_hour": int(os.getenv("DAILY_REPORT_HOUR", "8")),
    }


# ─── Helper ──────────────────────────────────────────────────────────────────
def is_daily_report_time(daily_hour: int) -> bool:
    """
    Trả về True nếu đang trong cửa sổ 30 phút đầu của giờ báo cáo (giờ VN).
    Đảm bảo báo cáo được gửi dù cron chạy lúc :00 hay :29.
    """
    now_vn = datetime.now(VN_TZ)
    return now_vn.hour == daily_hour and now_vn.minute < 30


# ─── Main ────────────────────────────────────────────────────────────────────
async def main() -> None:
    config = get_config()

    notifier = TelegramNotifier(
        token=config["telegram_token"],
        chat_id=config["telegram_chat_id"],
    )
    checker = VFSChecker(
        username=config["vfs_username"],
        password=config["vfs_password"],
        origin_country=config["origin_country"],
        target_country=config["target_country"],
        visa_category=config["visa_category"],
        visa_subcategory=config["visa_subcategory"],
    )

    now_vn = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    logger.info(f"[{now_vn} VN] Kiểm tra: {checker.origin_name} → {checker.target_name}")

    # ── Kiểm tra slot ────────────────────────────────────────────────────────
    slots = []
    error_msg = None

    try:
        slots = await checker.check_available_slots()
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Lỗi khi kiểm tra: {e}", exc_info=True)

    # ── Xử lý kết quả ────────────────────────────────────────────────────────
    if error_msg:
        await notifier.send_error(error_msg)
        sys.exit(1)

    if slots:
        logger.info(f"✅ Tìm thấy {len(slots)} trung tâm có lịch trống!")
        await notifier.send_slots_found(
            slots,
            origin_name=checker.origin_name,
            target_name=checker.target_name,
        )
    else:
        logger.info("❌ Không có lịch trống lần này.")

    # ── Báo cáo hàng ngày (nếu đúng giờ) ────────────────────────────────────
    if is_daily_report_time(config["daily_report_hour"]):
        logger.info("📊 Đúng giờ — gửi báo cáo hàng ngày...")
        await notifier.send_daily_report(
            slots=slots,
            origin_name=checker.origin_name,
            target_name=checker.target_name,
            total_checks=1,
            errors_today=0,
            booking_url=checker.portal_url,
        )

    logger.info("✅ Xong. GitHub Actions sẽ chạy lại theo lịch.")


if __name__ == "__main__":
    asyncio.run(main())
