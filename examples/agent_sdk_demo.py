#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio

from TALK.client import TalkClient


async def main() -> None:
    parser = argparse.ArgumentParser(description="TALK SDK demo agent")
    parser.add_argument("--name", default="demo")
    parser.add_argument("--key", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    member_id = f"agent:{args.name}"
    client = TalkClient(args.base_url, args.key)
    await client.register(member_id, display_name=f"Agent {args.name}")

    @client.on_message
    async def handle_message(message: dict) -> None:
        if message.get("type") != "text":
            return
        if "ping" not in (message.get("content") or "").lower():
            return
        await client.send_text("pong", to=[message["from"]])

    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
