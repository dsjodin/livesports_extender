"""Test: does a remote key sent over the network keep the Samsung TV's screen saver away?

The TV app cannot turn Samsung's screen saver off on the S95HF (OLED): it came after 2–4
min with every AppCommon attempt (docs/TV_APP.md, Screen saver). A key pressed on the
remote resets it. This sends one key every ``--every`` seconds through the TV's own
network remote (the Samsung remote-control WebSocket on port 8002, the one phone remote
apps use), so we can see whether that counts as a key press for the screen saver.

The key is KEY_RED by default: the TV's remote has no red key, the app registers it and
the graphics ignore it (web/tv/overlay.js), so it changes nothing on screen.

The first time, the TV asks whether to allow "SHL Arena": answer Allow with the remote.
The TV then gives a token, kept in ``<data dir>/tv_remote_token.txt`` so it does not ask
again.

    uv run --project server python tools/tv_keepawake.py 192.168.1.30
    docker compose exec arena python /srv/tools/tv_keepawake.py 192.168.1.30
    ... --every 60 --key KEY_RED --minutes 15

Ctrl+C stops it.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import ssl
import sys
import time
from pathlib import Path

import websockets

NAME = "SHL Arena"


def token_file() -> Path:
    root = Path(os.environ.get("ARENA_DATA_DIR") or Path(__file__).resolve().parent.parent / "data")
    return root / "tv_remote_token.txt"


def url(tv: str, token: str | None) -> str:
    name = base64.b64encode(NAME.encode()).decode()
    out = f"wss://{tv}:8002/api/v2/channels/samsung.remote.control?name={name}"
    return out + (f"&token={token}" if token else "")


def key_message(key: str) -> str:
    return json.dumps(
        {
            "method": "ms.remote.control",
            "params": {
                "Cmd": "Click",
                "DataOfCmd": key,
                "Option": "false",
                "TypeOfRemote": "SendRemoteKey",
            },
        }
    )


def stamp() -> str:
    return time.strftime("%H:%M:%S")


async def run(tv: str, key: str, every: float, minutes: float) -> int:
    tokens = token_file()
    token = tokens.read_text().strip() if tokens.exists() else None
    # the TV's certificate is its own, self-signed: no check (the LAN, our own TV)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    print(
        f"{stamp()} connecting to {tv}:8002",
        "(with a saved token)" if token else "(answer Allow on the TV)",
    )
    async with websockets.connect(
        url(tv, token), ssl=context, open_timeout=10, max_size=None
    ) as ws:
        while True:
            reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            event = reply.get("event")
            if event == "ms.channel.connect":
                new = (reply.get("data") or {}).get("token")
                if new and new != token:
                    tokens.parent.mkdir(parents=True, exist_ok=True)
                    tokens.write_text(new)
                    print(f"{stamp()} allowed; token saved in {tokens}")
                break
            if event == "ms.channel.timeOut":
                # seen on the S95HF at once, with no question on screen (2026-10-31)
                print(
                    f"{stamp()} the TV timed out without asking: leave the TV app (plain TV),",
                    "run this again and answer Allow; or allow SHL Arena in the TV's Device",
                    "Connection Manager (Device List)",
                    file=sys.stderr,
                )
                return 1
            if event == "ms.channel.unauthorized":
                print(
                    f"{stamp()} the TV said no (unauthorized): allow SHL Arena on the TV,",
                    f"or remove {tokens} and try again",
                    file=sys.stderr,
                )
                return 1
            print(f"{stamp()} {event}")
        print(f"{stamp()} connected; {key} every {every:g} s for {minutes:g} min (Ctrl+C stops)")
        end = time.monotonic() + minutes * 60
        sent = 0
        while time.monotonic() < end:
            await ws.send(key_message(key))
            sent += 1
            print(f"{stamp()} sent {key} ({sent})", flush=True)
            await asyncio.sleep(min(every, max(0.0, end - time.monotonic())))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("tv", help="the TV's IP address")
    parser.add_argument("--key", default="KEY_RED", help="the key to send (default KEY_RED)")
    parser.add_argument("--every", type=float, default=60, help="seconds between keys (default 60)")
    parser.add_argument("--minutes", type=float, default=15, help="how long to go on (default 15)")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.tv, args.key, args.every, args.minutes))
    except KeyboardInterrupt:
        return 0
    except (OSError, TimeoutError, websockets.WebSocketException) as err:
        print(
            f"{stamp()} no contact with the TV's remote on {args.tv}:8002: {err!r}", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
