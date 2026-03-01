"""
Visa Bot — GitHub Actions Edition (Multi-country)
Chạy MỘT LẦN: kiểm tra tất cả các nước → gửi Telegram → thoát.
GitHub Actions tự gọi lại mỗi 30 phút.
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("visa_bot")

# Múi giờ Việt Nam (UTC+7)
VN_TZ = timezone(timedelta(hours=7))


def get_config() -> dict:
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "VFS_USERNAME", "VFS_PASSWORD"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        logger.error(f"❌ Thiếu biến môi trường: {', '.join(missing)}")
        sys.exit(1)

    # Đọc danh sách nước, phân tách bằng dấu phẩy, bỏ khoảng trắng
    raw_countries = os.getenv("TARGET_COUNTRIES", "fra")
    target_countries = [c.strip().lower() for c in raw_countries.split(",") if c.strip()]

    return {
        "telegram_token":    os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_chat_id":  os.getenv("TELEGRAM_CHAT_ID"),
        "vfs_username":      os.getenv("VFS_USERNAME"),
        "vfs_password":      os.getenv("VFS_PASSWORD"),
        "origin_country":    os.getenv("ORIGIN_COUNTRY", "vnm"),
        "target_countries":  target_countries,
        "visa_category":     os.getenv("VISA_CATEGORY", "Tourist"),
        "visa_subcategory":  os.getenv("VISA_SUBCATEGORY", "Tourist Visa"),
        "daily_report_hour": int(os.getenv("DAILY_REPORT_HOUR", "12")),
    }


def is_daily_report_time(daily_hour: int) -> bool:
    now_vn = datetime.now(VN_TZ)
    return now_vn.hour == daily_hour and now_vn.minute < 30


async def check_one_country(
    country: str,
    config: dict,
    notifier: TelegramNotifier,
) -> dict:
    """Kiểm tra một nước, trả về kết quả."""
    checker = VFSChecker(
        username=config["vfs_username"],
        password=config["vfs_password"],
        origin_country=config["origin_country"],
        target_country=country,
        visa_category=config["visa_category"],
        visa_subcategory=config["visa_subcategory"],
    )

    logger.info(f"  → Kiểm tra {checker.target_name}...")
    try:
        slots = await checker.check_available_slots()
        return {
            "country": country,
            "name": checker.target_name,
            "slots": slots,
            "portal_url": checker.portal_url,
            "error": None,
            "checker": checker,
        }
    except Exception as e:
        logger.error(f"  ✗ Lỗi {checker.target_name}: {e}")
        return {
            "country": country,
            "name": checker.target_name,
            "slots": [],
            "portal_url": checker.portal_url,
            "error": str(e),
            "checker": checker,
        }


async def main() -> None:
    config = get_config()
    countries = config["target_countries"]

    notifier = TelegramNotifier(
        token=config["telegram_token"],
        chat_id=config["telegram_chat_id"],
    )
await notifier.send_test()
logger.info("✅ Xong. GitHub Actions sẽ chạy lại sau 30 phút.")
    now_vn = datetime.now(VN_TZ).strftime("%d/%m/%Y %H:%M")
    logger.info(f"[{now_vn} VN] Kiểm tra {len(countries)} nước: {', '.join(countries).upper()}")

    # ── Kiểm tra từng nước ────────────────────────────────────────────────────
    # Chạy tuần tự để tránh bị VFS chặn vì quá nhiều request đồng thời
    results = []
    for country in countries:
        result = await check_one_country(country, config, notifier)
        results.append(result)
        await asyncio.sleep(3)  # Nghỉ 3 giây giữa các nước

    # ── Gửi thông báo lịch trống (nếu có) ────────────────────────────────────
    found_any = False
    for r in results:
        if r["error"]:
            continue
        if r["slots"]:
            found_any = True
            checker = r["checker"]
            await notifier.send_slots_found(
                r["slots"],
                origin_name=checker.origin_name,
                target_name=checker.target_name,
            )
            logger.info(f"  ✅ {r['name']}: {len(r['slots'])} trung tâm có lịch!")

    if not found_any:
        logger.info("❌ Không có lịch trống ở bất kỳ nước nào.")

    # ── Thông báo lỗi (nếu có) ────────────────────────────────────────────────
    errors = [r for r in results if r["error"]]
    if errors:
        error_summary = "\n".join(f"• {r['name']}: {r['error']}" for r in errors)
        await notifier.send_error(error_summary, context="kiểm tra đa quốc gia")

    # ── Báo cáo hàng ngày (nếu đúng giờ) ────────────────────────────────────
    if is_daily_report_time(config["daily_report_hour"]):
        logger.info("📊 Đúng giờ — gửi báo cáo tổng hợp hàng ngày...")
        await send_combined_daily_report(results, config, notifier)

    logger.info("✅ Xong. GitHub Actions sẽ chạy lại sau 30 phút.")


async def send_combined_daily_report(results: list, config: dict, notifier: TelegramNotifier) -> None:
    """Gửi báo cáo tổng hợp tất cả các nước trong một tin nhắn."""
    now_vn = datetime.now(VN_TZ)
    date_str = now_vn.strftime("%d/%m/%Y")

    lines = [
        f"📊 <b>Báo cáo ngày {date_str}</b>",
        f"🕐 {now_vn.strftime('%H:%M')} giờ Việt Nam\n",
    ]

    has_slots = False
    for r in results:
        if r["error"]:
            lines.append(f"🔴 <b>{r['name']}</b> — Lỗi kết nối")
        elif r["slots"]:
            has_slots = True
            earliest = r["slots"][0].get("earliest_date", "?") if r["slots"] else "?"
            lines.append(f"🟢 <b>{r['name']}</b> — Có lịch trống! Sớm nhất: <b>{earliest}</b>")
            lines.append(f"   🔗 <a href='{r['portal_url']}'>Đặt lịch ngay</a>")
        else:
            lines.append(f"🟡 <b>{r['name']}</b> — Chưa có lịch trống")

    if not has_slots:
        lines.append("\n💡 <i>Chưa có lịch trống hôm nay. Bot tiếp tục theo dõi.</i>")
    else:
        lines.append("\n⚡ <b>Vào đặt lịch ngay trước khi hết!</b>")

    # Dùng trực tiếp httpx thay vì gọi lại send_daily_report
    import httpx
    text = "\n".join(lines)
    url = f"https://api.telegram.org/bot{config['telegram_token']}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        await client.post(url, json={
            "chat_id": config["telegram_chat_id"],
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        })


if __name__ == "__main__":
    asyncio.run(main())
