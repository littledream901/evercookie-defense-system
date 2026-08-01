"""密码哈希服务。

直接使用 bcrypt 原生 API，不经 passlib：
passlib 1.7.x 通过 `bcrypt.__about__.__version__` 探测后端版本，而 bcrypt >= 4.1
已移除该属性，探测失败会让 verify/hash 抛 ValueError——表现为「所有登录都失败」。
"""

from __future__ import annotations

import re

import bcrypt

_MAX_BCRYPT_BYTES = 72
"""bcrypt 算法上限：超过 72 字节的部分会被静默丢弃，新版库直接报错。"""


class PasswordService:
    def hash(self, password: str) -> str:
        self.validate_strength(password)
        return bcrypt.hashpw(self._to_bytes(password), bcrypt.gensalt()).decode("utf-8")

    def verify(self, password: str, password_hash: str) -> bool:
        if not password or not password_hash:
            return False
        try:
            return bcrypt.checkpw(
                self._to_bytes(password), password_hash.encode("utf-8")
            )
        except (ValueError, TypeError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        """非 bcrypt 格式（或 cost 低于当前默认值）时需要重新哈希。"""
        if not password_hash.startswith(("$2a$", "$2b$", "$2y$")):
            return True
        try:
            cost = int(password_hash.split("$")[2])
        except (IndexError, ValueError):
            return True
        return cost < 12

    @staticmethod
    def _to_bytes(password: str) -> bytes:
        return password.encode("utf-8")[:_MAX_BCRYPT_BYTES]

    @staticmethod
    def validate_strength(password: str) -> None:
        """验证密码强度：至少 8 字符，包含大小写字母和数字。"""
        if not password or len(password) < 8:
            raise ValueError("密码长度不能少于 8 位")
        if not re.search(r"[a-z]", password):
            raise ValueError("密码必须包含小写字母")
        if not re.search(r"[A-Z]", password):
            raise ValueError("密码必须包含大写字母")
        if not re.search(r"\d", password):
            raise ValueError("密码必须包含数字")
