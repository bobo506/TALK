"""Create the first human admin directly in the database."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.db import engine, init_db  # noqa: E402
from server.models import Member  # noqa: E402
from server.routes.members import count_human_members  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the first TALK human admin directly in the database."
    )
    parser.add_argument("--id", dest="member_id", help="Member id, for example human:bobo")
    parser.add_argument("--name", dest="display_name", help="Display name, for example Bobo")
    parser.add_argument("--key", dest="api_key", help="API key for the new admin")
    args = parser.parse_args()

    provided = [args.member_id, args.display_name, args.api_key]
    if any(provided) and not all(provided):
        parser.error("--id, --name, and --key must be provided together")
    return args


def prompt_non_empty(prompt: str, *, secret: bool = False) -> str:
    while True:
        value = getpass.getpass(prompt) if secret else input(prompt)
        value = value.strip()
        if value:
            return value
        print("Value cannot be empty.", file=sys.stderr)


def create_admin_member(
    session: Session,
    *,
    member_id: str,
    display_name: str,
    api_key: str,
) -> Member:
    if not member_id.startswith("human:"):
        raise ValueError("id must start with 'human:'")

    if count_human_members(session) > 0:
        raise RuntimeError("管理员已存在，请走正常注册流程")

    existing_id = session.get(Member, member_id)
    if existing_id is not None:
        raise RuntimeError(f"Member '{member_id}' already exists")

    existing_key = session.exec(
        select(Member).where(Member.api_key == api_key)
    ).first()
    if existing_key is not None:
        raise RuntimeError(f"API key already in use by '{existing_key.id}'")

    member = Member(
        id=member_id,
        kind="human",
        display_name=display_name,
        api_key=api_key,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def main() -> int:
    args = parse_args()
    interactive = not any([args.member_id, args.display_name, args.api_key])

    if interactive:
        member_id = prompt_non_empty("Admin id (human:...): ")
        display_name = prompt_non_empty("Display name: ")
        api_key = prompt_non_empty("API key: ", secret=True)
    else:
        member_id = args.member_id.strip()
        display_name = args.display_name.strip()
        api_key = args.api_key.strip()

    try:
        init_db()
        with Session(engine) as session:
            member = create_admin_member(
                session,
                member_id=member_id,
                display_name=display_name,
                api_key=api_key,
            )
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if interactive:
        print(f"Created admin '{member.id}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
