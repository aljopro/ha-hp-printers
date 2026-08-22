"""Capture LEDM XML from a live printer for use as test fixtures.

Run this from a machine on the same network as the printer. It fetches the
endpoints the integration reads and writes each response under
``scripts/captures/<host>-<timestamp>/`` so it can be reviewed and
anonymized before being committed.

Usage:
    ./.venv/bin/python scripts/capture_ledm.py --host 192.168.0.64
    ./.venv/bin/python scripts/capture_ledm.py --host printer.local --port 8080
    ./.venv/bin/python scripts/capture_ledm.py --host 192.168.0.64 --output ./raw

The script is read-only: every request is a ``GET``. Some printers may rate
limit or refuse traffic from unknown User-Agents, so we send a normal
browser-like header and sleep briefly between requests.
"""

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

ENDPOINTS = (
    "/DevMgmt/ProductConfigDyn.xml",
    "/DevMgmt/ProductStatusDyn.xml",
    "/DevMgmt/ProductUsageDyn.xml",
    "/DevMgmt/ConsumableConfigDyn.xml",
    "/DevMgmt/ProductLogsDyn.xml",
    "/DevMgmt/IOConfigDyn.xml",
    "/DevMgmt/DiscoveryTree.xml",
)


async def capture(host: str, port: int, scheme: str, output: Path) -> None:
    """Fetch every LEDM endpoint and save the responses."""
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target_dir = output / f"{host}-{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=True)

    base = f"{scheme}://{host}:{port}"
    headers = {"User-Agent": "ha-hp-printers capture/1.0"}

    timeout = aiohttp.ClientTimeout(total=20)
    ssl_context = False if scheme == "http" else None

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for endpoint in ENDPOINTS:
            url = f"{base}{endpoint}"
            filename = endpoint.lstrip("/").replace("/", "_")
            target = target_dir / filename
            print(f"GET {url} -> {target}")  # noqa: T201
            try:
                async with session.get(url, ssl=ssl_context) as response:
                    response.raise_for_status()
                    body = await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                print(f"  failed: {exc}")  # noqa: T201
                continue

            target.write_text(body, encoding="utf-8")
            # Brief pause so we do not trigger rate limiting on tight loops.
            await asyncio.sleep(0.5)

    print(f"\nCaptured {len(ENDPOINTS)} endpoints into {target_dir}")  # noqa: T201


def main() -> None:
    """Parse arguments and run the capture."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Printer hostname or IP")
    parser.add_argument("--port", type=int, default=80, help="HTTP port (default 80)")
    parser.add_argument(
        "--https",
        action="store_true",
        help=(
            "Use HTTPS. The default is HTTP. Note: printers usually serve "
            "self-signed certificates."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scripts/captures"),
        help="Directory to write captures into",
    )
    args = parser.parse_args()

    asyncio.run(
        capture(
            host=args.host,
            port=args.port,
            scheme="https" if args.https else "http",
            output=args.output,
        )
    )


if __name__ == "__main__":
    main()
