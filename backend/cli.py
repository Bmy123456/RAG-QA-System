"""
CLI 管理工具：用户管理、数据导出等运维操作。

用法:
    python -m backend.cli make-admin <用户名>
    python -m backend.cli list-users
    python -m backend.cli reset-password <用户名> <新密码>
"""

from __future__ import annotations

import argparse
import sys

from backend.db.session import SessionLocal, init_db
from backend.models.user import User


def _get_db():
    init_db()
    return SessionLocal()


def cmd_make_admin(args: argparse.Namespace) -> None:
    """将指定用户提升为管理员。"""
    db = _get_db()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if not user:
            print(f"错误: 用户 '{args.username}' 不存在")
            sys.exit(1)

        if user.role == "admin":
            print(f"用户 '{args.username}' 已经是管理员，无需重复设置")
            return

        user.role = "admin"
        db.commit()
        print(f"已将用户 '{args.username}' (id={user.id}) 提升为管理员")
    finally:
        db.close()


def cmd_list_users(args: argparse.Namespace) -> None:
    """列出所有用户。"""
    db = _get_db()
    try:
        users = db.query(User).order_by(User.id).all()
        if not users:
            print("暂无用户")
            return

        print(f"{'ID':<6} {'用户名':<20} {'角色':<10} {'状态':<8} {'创建时间'}")
        print("-" * 65)
        for u in users:
            status = "正常" if u.is_active else "已禁用"
            created = u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else "-"
            print(f"{u.id:<6} {u.username:<20} {u.role:<10} {status:<8} {created}")
    finally:
        db.close()


def cmd_reset_password(args: argparse.Namespace) -> None:
    """重置用户密码。"""
    from backend.api.auth import _hash_password, _check_password_strength

    err = _check_password_strength(args.password)
    if err:
        print(f"密码不符合要求: {err}")
        sys.exit(1)

    db = _get_db()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if not user:
            print(f"错误: 用户 '{args.username}' 不存在")
            sys.exit(1)

        user.hashed_password = _hash_password(args.password)
        db.commit()
        print(f"已重置用户 '{args.username}' 的密码")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="RAG 系统管理工具",
        prog="python -m backend.cli",
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # make-admin
    p_admin = sub.add_parser("make-admin", help="将用户提升为管理员")
    p_admin.add_argument("username", help="目标用户名")
    p_admin.set_defaults(func=cmd_make_admin)

    # list-users
    p_list = sub.add_parser("list-users", help="列出所有用户")
    p_list.set_defaults(func=cmd_list_users)

    # reset-password
    p_reset = sub.add_parser("reset-password", help="重置用户密码")
    p_reset.add_argument("username", help="目标用户名")
    p_reset.add_argument("password", help="新密码（至少 8 位，含大小写字母和数字）")
    p_reset.set_defaults(func=cmd_reset_password)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
