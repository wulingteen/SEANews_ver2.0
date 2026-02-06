#!/usr/bin/env python3
"""
Validate required environment variables for SEA News deployment.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List

try:
    import dotenv
except ImportError:
    dotenv = None


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"

REQUIRED_KEYS = [
    "OPENAI_API_KEY",
    "APP_USERNAME",
    "APP_PASSWORD",
    "APP_SECRET_KEY",
    "SMTP_SERVER",
    "SMTP_PORT",
    "EMAIL_ADDRESS",
    "EMAIL_PASSWORD",
]

DOMAIN_PATTERN = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$", re.IGNORECASE)


def parse_csv(raw: str) -> List[str]:
    return [item.strip() for item in (raw or "").split(",") if item.strip()]


def validate_smtp_port(value: str) -> bool:
    if not value or not value.isdigit():
        return False
    port = int(value)
    return 1 <= port <= 65535


def main() -> int:
    if dotenv is not None:
        dotenv.load_dotenv(ENV_PATH, override=False)
    elif ENV_PATH.exists():
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    errors: List[str] = []
    warnings: List[str] = []

    for key in REQUIRED_KEYS:
        if not os.getenv(key, "").strip():
            errors.append(f"Missing required key: {key}")

    smtp_port = os.getenv("SMTP_PORT", "").strip()
    if smtp_port and not validate_smtp_port(smtp_port):
        errors.append("SMTP_PORT must be an integer between 1 and 65535")

    google_client_front = os.getenv("VITE_GOOGLE_CLIENT_ID", "").strip()
    google_client_back = os.getenv("GOOGLE_CLIENT_ID", "").strip()

    if google_client_back:
        if google_client_front and google_client_front != google_client_back:
            warnings.append(
                "VITE_GOOGLE_CLIENT_ID differs from GOOGLE_CLIENT_ID; frontend will use runtime config from backend"
            )
    elif google_client_front:
        warnings.append(
            "VITE_GOOGLE_CLIENT_ID is set but GOOGLE_CLIENT_ID is empty; Google login verification will fail on backend"
        )
    else:
        warnings.append("Google OAuth is disabled (client IDs are empty)")

    allowed_domains = parse_csv(os.getenv("GOOGLE_ALLOWED_DOMAINS", ""))
    invalid_domains = [domain for domain in allowed_domains if not DOMAIN_PATTERN.match(domain)]
    if invalid_domains:
        errors.append(
            "GOOGLE_ALLOWED_DOMAINS contains invalid domain(s): "
            + ", ".join(invalid_domains)
        )

    print("SEA News env validation")
    print(f"- .env path: {ENV_PATH}")
    print(f"- Required keys checked: {len(REQUIRED_KEYS)}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("\nValidation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nValidation passed: environment configuration looks good.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
