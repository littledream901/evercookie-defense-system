"""行为时序：领域词汇与乱序修复的纯函数。

分层约定
--------
本包**不依赖 pydantic，也不导入 ``fangyu_shared.schemas``**。原因是
``schemas.decision`` 需要引用行为事件契约，若本包反向导入 schemas 就会形成
循环导入。因此这里只放领域词汇（枚举）与纯函数，wire 契约
:class:`fangyu_shared.schemas.behavior.BehaviorEvent` 放在 schemas 侧。

乱序修复的原理
--------------
ZSet 的 score 取**客户端上报的事件时间经服务端归一化后的值**，而不是服务端
接收时间。网络抖动导致的迟到事件会自动落到正确的时序位置上，``ZRANGE`` 出来
即为真实发生顺序，不需要额外重排逻辑。

为什么必须夹取客户端时间
------------------------
score 直接来自客户端就等于把排序权交给了客户端。恶意端只要上报一个极大的
时间戳，就能让自己的事件永远排在最后，而按 rank 淘汰最旧数据的裁剪逻辑会把
真实事件全部挤掉。因此所有客户端时间都必须夹取到服务端时间的合理邻域内。
"""

from __future__ import annotations

import uuid
from enum import Enum

MAX_CLIENT_SKEW_MS = 300_000
"""允许的客户端时钟偏移：±5 分钟。超出即夹取到服务端时间。"""


class BehaviorKind(str, Enum):
    """行为事件类型。

    只收敛到风控真正需要的几类。采集端可以上报更细的类型，但落到网关一律
    映射进这个枚举——枚举外的类型会被拒绝，避免采集端随意扩张字段拖垮存储。
    """

    PAGE_VIEW = "page_view"
    CLICK = "click"
    MOUSE_MOVE = "mouse_move"
    SCROLL = "scroll"
    KEY_PRESS = "key_press"
    FOCUS = "focus"
    BLUR = "blur"
    SUBMIT = "submit"


def normalize_event_time(client_ts_ms: int, *, server_now_ms: int) -> int:
    """把客户端事件时间夹取到服务端时间的合理邻域。

    偏移超过 :data:`MAX_CLIENT_SKEW_MS` 的一律取服务端时间——此时客户端时钟
    不可信，用服务端时间至少能保证相对顺序不被恶意操纵。
    """
    if client_ts_ms <= 0:
        return server_now_ms
    lower = server_now_ms - MAX_CLIENT_SKEW_MS
    upper = server_now_ms + MAX_CLIENT_SKEW_MS
    if client_ts_ms < lower or client_ts_ms > upper:
        return server_now_ms
    return client_ts_ms


def make_member(event_ts_ms: int, kind: BehaviorKind) -> str:
    """构造 ZSet member。

    带 nonce 保证同毫秒同类型的多个事件不会互相覆盖。旧版用「毫秒取模」当
    序号，同毫秒的两条片段 member 完全相同而被 ZSet 静默去重吞掉。
    """
    return f"{event_ts_ms}:{kind.value}:{uuid.uuid4().hex[:8]}"
