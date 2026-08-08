"""挑战凭据的签发与校验。

Challenge 闭环：
1. gateway 签发 token → 下发给客户端（SDK / 适配器）
2. 客户端完成挑战 → 携带 token 提交答案
3. gateway 校验 token → 验签 + 过期时间 + nonce 防重放

Token 格式（HMAC-SHA256 签名）：
    payload = {
        "appId": int,
        "fingerprint": str,
        "kind": "captcha" | "js_challenge",
        "exp": int,  # Unix timestamp (秒)
        "nonce": str  # 32 hex
    }
    token = base64(json(payload)) + "." + hmac_sha256(app_secret, payload_base64)

为什么不用 JWT：
- 标准 JWT 库会引入多余的算法支持（RS256 / ES256 / EdDSA），增加攻击面
- 我们只需 HS256 + 最小载荷，自实现比依赖第三方库更轻
- payload 按字典序编码，与 build_sign_payload 口径统一
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Literal

from fangyu_shared.utils.crypto import constant_time_compare, generate_nonce, hmac_sha256

ChallengeKind = Literal["captcha", "js_challenge"]

DEFAULT_TTL = 300
"""挑战凭据默认有效期（秒），与决策缓存 TTL 对齐。"""


@dataclass(slots=True)
class ChallengeTokenPayload:
    """挑战凭据载荷。"""

    site_id: int
    fingerprint: str
    kind: ChallengeKind
    exp: int  # Unix timestamp (秒)
    nonce: str
    difficulty: int = 4
    """js_challenge 的 PoW 难度（哈希前导零位数）。客户端必须据此计算，服务端用此值验证。"""

    def to_dict(self) -> dict:
        return {
            "siteId": self.site_id,
            "fingerprint": self.fingerprint,
            "kind": self.kind,
            "exp": self.exp,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChallengeTokenPayload:
        # 兼容改名前签发的在途 token（TTL 5 分钟，滚动发布期间会同时存在两种键名）
        raw_site_id = d["siteId"] if "siteId" in d else d["appId"]
        return cls(
            site_id=int(raw_site_id),
            fingerprint=str(d["fingerprint"]),
            kind=str(d["kind"]),  # type: ignore
            exp=int(d["exp"]),
            nonce=str(d["nonce"]),
            difficulty=int(d.get("difficulty", 4)),  # 兼容旧 token
        )


def issue_challenge_token(
    *,
    site_id: int,
    fingerprint: str,
    kind: ChallengeKind,
    secret: str,
    ttl: int = DEFAULT_TTL,
    difficulty: int = 4,
) -> str:
    """签发挑战凭据。

    Args:
        site_id: 站点 ID（Site.id）
        fingerprint: 访客指纹，防跨访客盗用
        kind: 挑战类型
        secret: 站点密钥（site_secret）
        ttl: 有效期（秒）
        difficulty: js_challenge 的 PoW 难度（哈希前导零位数）

    Returns:
        base64(payload) + "." + hmac_sha256(secret, base64_payload)
    """
    payload = ChallengeTokenPayload(
        site_id=site_id,
        fingerprint=fingerprint,
        kind=kind,
        exp=int(time.time()) + ttl,
        nonce=generate_nonce(),
        difficulty=difficulty,
    )
    # 紧凑 JSON（无空格）+ 键排序，保证签名稳定
    payload_json = json.dumps(payload.to_dict(), sort_keys=True, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii")
    # 去掉尾部 padding（= 号），减少 URL 编码开销
    payload_b64 = payload_b64.rstrip("=")
    signature = hmac_sha256(secret, payload_b64)
    return f"{payload_b64}.{signature}"


@dataclass(slots=True)
class TokenVerifyResult:
    """Token 校验结果。"""

    valid: bool
    payload: ChallengeTokenPayload | None = None
    reason: str | None = None
    """校验失败原因：malformed | expired | signature_mismatch"""


def verify_challenge_token(
    token: str,
    *,
    secret: str,
    site_id: int,
    fingerprint: str,
) -> TokenVerifyResult:
    """校验挑战凭据。

    Args:
        token: 客户端提交的凭据
        secret: 站点密钥（site_secret）
        site_id: 当前请求的 site_id（必须与 token 中的一致）
        fingerprint: 当前请求的指纹（必须与 token 中的一致）

    Returns:
        校验结果。valid=True 时 payload 非 None。
    """
    if not token or "." not in token:
        return TokenVerifyResult(valid=False, reason="malformed")

    parts = token.split(".", 1)
    if len(parts) != 2:
        return TokenVerifyResult(valid=False, reason="malformed")

    payload_b64, signature = parts

    # 验签（常量时间比较）
    expected_sig = hmac_sha256(secret, payload_b64)
    if not constant_time_compare(signature, expected_sig):
        return TokenVerifyResult(valid=False, reason="signature_mismatch")

    # 解码 payload（补齐 padding）
    padding = (4 - len(payload_b64) % 4) % 4
    payload_b64_padded = payload_b64 + "=" * padding
    try:
        payload_json = base64.urlsafe_b64decode(payload_b64_padded).decode("utf-8")
        payload_dict = json.loads(payload_json)
        payload = ChallengeTokenPayload.from_dict(payload_dict)
    except (ValueError, KeyError, json.JSONDecodeError):
        return TokenVerifyResult(valid=False, reason="malformed")

    # 过期检查
    if payload.exp < int(time.time()):
        return TokenVerifyResult(valid=False, payload=payload, reason="expired")

    # site_id 与 fingerprint 必须与当前请求一致，防跨租户 / 跨访客盗用
    if payload.site_id != site_id:
        return TokenVerifyResult(valid=False, payload=payload, reason="site_mismatch")
    if payload.fingerprint != fingerprint:
        return TokenVerifyResult(valid=False, payload=payload, reason="fingerprint_mismatch")

    return TokenVerifyResult(valid=True, payload=payload)
