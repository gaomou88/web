"""应急命令（在服务器上运行）：

  docker exec zyll python -m app.cli disable-turnstile   关闭所有 Cloudflare 人机验证
  docker exec zyll python -m app.cli reset-admin          删除所有管理员，下次访问 /zylladmin 重新进入安装向导
  docker exec zyll python -m app.cli list-admins          列出管理员

修改后执行 docker restart zyll 生效。
"""
from __future__ import annotations

import asyncio
import json
import sys

from . import store


async def main(cmd: str) -> int:
    await store.init()
    if cmd == "disable-turnstile":
        for key in ("turnstile.on_register", "turnstile.on_login", "turnstile.on_admin_login"):
            await store.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                                (key, json.dumps(False)))
        print("已关闭所有 Cloudflare 人机验证。请运行 docker restart zyll")
    elif cmd == "reset-admin":
        await store.execute("DELETE FROM admins")
        print("已删除所有管理员。请运行 docker restart zyll，然后访问 /zylladmin 重新安装")
    elif cmd == "list-admins":
        for a in await store.query("SELECT id, username FROM admins"):
            print(a["id"], a["username"])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "")))
