"""启动级配置：只有数据目录、前端目录和会话密钥。其余设置都在后台里改。"""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(os.environ.get("DATA_DIR", "/data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "zyll.db"
        default_fe = Path(__file__).resolve().parents[2] / "frontend"
        self.frontend_dir = Path(os.environ.get("FRONTEND_DIR", str(default_fe)))
        self.secret_key = os.environ.get("SECRET_KEY") or self._load_secret()

    def _load_secret(self) -> str:
        """首次启动自动生成密钥并保存在数据目录，之后一直沿用。"""
        path = self.data_dir / "secret.key"
        if path.exists():
            return path.read_text().strip()
        key = secrets.token_hex(32)
        path.write_text(key)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return key


@lru_cache
def get_settings() -> Settings:
    return Settings()
