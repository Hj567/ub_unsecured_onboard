#!/usr/bin/env bash
set -e

echo "Upgrading pip/setuptools/wheel..."
pip install --upgrade pip setuptools wheel

echo "Installing Python deps..."
pip install -r requirements.txt

echo "Installing Playwright Chromium with dependencies..."
python -m playwright install --with-deps chromium