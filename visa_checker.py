name: 🛂 Visa Slot Checker

on:
  schedule:
    - cron: '*/30 * * * *'
  workflow_dispatch:

jobs:
  check-visa:
    name: Kiểm tra lịch VFS Global
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: 📥 Checkout code
        uses: actions/checkout@v4

      - name: 🐍 Cài Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: 📦 Cài dependencies
        run: pip install -r requirements.txt

      - name: 🤖 Chạy Visa Bot
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID:   ${{ secrets.TELEGRAM_CHAT_ID }}
          VFS_USERNAME:       ${{ secrets.VFS_USERNAME }}
          VFS_PASSWORD:       ${{ secrets.VFS_PASSWORD }}
          ORIGIN_COUNTRY:     ${{ vars.ORIGIN_COUNTRY }}
          TARGET_COUNTRIES:   ${{ vars.TARGET_COUNTRIES }}
          VISA_CATEGORY:      ${{ vars.VISA_CATEGORY }}
          VISA_SUBCATEGORY:   ${{ vars.VISA_SUBCATEGORY }}
          DAILY_REPORT_HOUR:  ${{ vars.DAILY_REPORT_HOUR }}
        run: python main.py
