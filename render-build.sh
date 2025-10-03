#!/usr/bin/env bash
set -e

echo "Installing Python deps..."
pip install -r requirements.txt

echo "Installing Playwright Chromium..."
python -m playwright install chromium

pip install --upgrade pip setuptools wheel
pip install pandas