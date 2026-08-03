"""基础安全检查：黑名单、地理围栏、代理拦截等。"""

from __future__ import annotations

from dataclasses import dataclass

from fangyu_shared.schemas.disposition import Disposition, deny, not_found

from src.domain.profile.builder import ProfileSnapshot


@dataclass(frozen=True, slots=True)
class SecurityCheckResult:
    triggered: bool
    disposition: Disposition | None = None
    reason: str | None = None
    score_delta: float = 0.0


class SecurityChecker:
    """安全策略检查器。命中即返回，跳过后续流水线。"""

    def __init__(
        self,
        *,
        ip_blacklist: set[str] | None = None,
        country_blocklist: set[str] | None = None,
        block_tor: bool = True,
    ) -> None:
        self._ip_blacklist = ip_blacklist or set()
        self._country_blocklist = {c.upper() for c in (country_blocklist or set())}
        self._block_tor = block_tor

    def check(self, snapshot: ProfileSnapshot) -> SecurityCheckResult:
        ip = snapshot.ip
        if ip.ip in self._ip_blacklist:
            return SecurityCheckResult(
                triggered=True,
                disposition=deny(),
                reason="ip_blacklist",
            )
        country = (ip.country or "").upper()
        if country and country in self._country_blocklist:
            return SecurityCheckResult(
                triggered=True,
                disposition=deny(),
                reason=f"country_blocked:{country}",
            )
        if self._block_tor and ip.is_tor:
            # Tor 用 404 而非 403：不暴露「你被识别了」，降低对抗升级动机
            return SecurityCheckResult(
                triggered=True,
                disposition=not_found(),
                reason="tor_exit_node",
            )

        # ── 以下两条是硬判定，不交给评分累积 ──
        # 高置信信号靠分数累积拦截是不可靠的：只要阈值上调或新增 scorer，
        # 它们就可能掉到线下。误杀风险本身极低的信号应当直接判死。
        ua = snapshot.ua
        if ua is not None and ua.crawler_category == "security":
            # 漏洞扫描器（sqlmap / nikto 等）没有任何正常业务用途
            return SecurityCheckResult(
                triggered=True,
                disposition=deny(),
                reason=f"security_scanner:{ua.crawler_vendor or 'unknown'}",
            )

        if ip.is_vpn and ip.is_datacenter:
            # VPN 且数据中心：真实访客的 VPN 出口通常落在住宅或运营商段，
            # 两者同时成立基本只有自建代理与爬虫池。
            return SecurityCheckResult(
                triggered=True,
                disposition=deny(),
                reason="vpn_on_datacenter",
            )

        return SecurityCheckResult(triggered=False)
