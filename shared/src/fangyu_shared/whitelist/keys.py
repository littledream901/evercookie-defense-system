"""白名单键构造。唯一真相来源，admin 写与 gateway 读都从这里导入。

数据结构：单个 Hash
------------------
``fangyu:whitelist:{app_id}`` 是一个 Hash，field 形如 ``ip:1.2.3.4`` /
``fp:abc123``，value 是 JSON 元信息（备注、创建人、创建时间）。

为什么用 Hash 而不是两个 Set
----------------------------
gateway 每个请求要同时判断 IP 与指纹两条轴。Set 方案需要两次 ``SISMEMBER``；
Hash 方案一次 ``HMGET`` 拿两个 field，往返减半。而且 Set 只能存成员、放不下
「谁在什么时候为什么加的」——白名单是绕过全部风控的高危配置，没有审计信息
时无法回答「这条为什么在里面」，运维久了就只能全删重建。

为什么 IP 存明文而封禁存哈希
----------------------------
封禁键的 IP 走 ``sha256_hex(ip)[:32]``（见 ``clock.windows.ban_key`` 的调用
方），白名单刻意不哈希：

1. 白名单是**运维手工录入**的。要求运维先算一遍 SHA256 才能放行自家办公网
   出口 IP，等于把这个功能废掉。
2. 哈希的动机是频控键里不落明文 IP（数量大、留存久）。白名单是显式的准入
   声明，条目少且本就由人可读地维护，隐私论据不成立。

代价是 gateway 侧不能复用已算好的 ``ip_hash``，要用原始 IP 查一次。这是有
意的取舍，改动时不要「顺手统一」成哈希——那会让所有已录入的白名单静默失效。

不支持 CIDR
-----------
只做精确匹配。CIDR 需要遍历全部条目做网段包含判断，O(1) 查询退化成
O(n)，而白名单在**每个请求**的最前面执行。需要放行整个网段时录入具体出口
IP，或走决策规则的 allowlist 组。
"""

from __future__ import annotations

from enum import Enum

_KEY_PREFIX = "fangyu:whitelist"


class WhitelistDimension(str, Enum):
    """白名单维度。

    取值与 :class:`fangyu_shared.clock.windows.ClockDimension` 故意保持一致
    （``ip`` / ``fp``），这样前端的维度下拉框、审计日志的维度字段在封禁与
    白名单两处含义相同。但不直接复用那个枚举——白名单不依赖频控，共用会
    让「改频控维度」意外波及白名单。
    """

    IP = "ip"
    FINGERPRINT = "fp"


def whitelist_key(app_id: int) -> str:
    """某 app 的白名单 Hash 键。"""
    return f"{_KEY_PREFIX}:{app_id}"


def field_name(dimension: WhitelistDimension, value: str) -> str:
    """Hash field 名。"""
    return f"{dimension.value}:{value}"


def parse_field(field: str) -> tuple[WhitelistDimension, str] | None:
    """把 Hash field 名还原成 ``(维度, 值)``。

    无法识别的 field 返回 ``None`` 而不抛异常：列表接口不能因为 Redis 里
    混进一条脏数据就整个 500，那样运维连删掉它的入口都没有。

    只按第一个 ``:`` 切分——指纹与 IPv6 的值本身可能含冒号。
    """
    dim_raw, sep, value = field.partition(":")
    if not sep or not value:
        return None
    try:
        dimension = WhitelistDimension(dim_raw)
    except ValueError:
        return None
    return dimension, value
