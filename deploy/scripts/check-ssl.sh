#!/usr/bin/env bash
# =============================================================================
# SSL 证书与对外链路校验
# -----------------------------------------------------------------------------
# 用法：
#   bash deploy/scripts/check-ssl.sh admin.example.com defense.example.com
#
# 可挂到 1Panel 计划任务每日执行，证书剩余不足 15 天时退出码非 0。
# =============================================================================
set -uo pipefail

WARN_DAYS="${WARN_DAYS:-15}"
FAIL=0

if [[ $# -eq 0 ]]; then
    echo "用法：bash $0 <域名> [域名...]" >&2
    exit 2
fi

for domain in "$@"; do
    printf '\n\033[1m%s\033[0m\n' "$domain"

    # 证书有效期
    CERT="$(echo | timeout 10 openssl s_client -servername "$domain" \
            -connect "${domain}:443" 2>/dev/null | openssl x509 -noout -dates -subject 2>/dev/null)"

    if [[ -z "$CERT" ]]; then
        printf '\033[31m  ✗ 无法建立 TLS 连接（证书未配置或 443 不可达）\033[0m\n'
        FAIL=1
        continue
    fi

    NOT_AFTER="$(echo "$CERT" | grep -oP 'notAfter=\K.*')"
    EXPIRY_TS="$(date -d "$NOT_AFTER" +%s 2>/dev/null || echo 0)"
    NOW_TS="$(date +%s)"
    DAYS_LEFT=$(( (EXPIRY_TS - NOW_TS) / 86400 ))

    if [[ "$EXPIRY_TS" == "0" ]]; then
        printf '\033[31m  ✗ 无法解析到期时间\033[0m\n'
        FAIL=1
    elif [[ "$DAYS_LEFT" -lt 0 ]]; then
        printf '\033[31m  ✗ 证书已过期（%s）\033[0m\n' "$NOT_AFTER"
        FAIL=1
    elif [[ "$DAYS_LEFT" -lt "$WARN_DAYS" ]]; then
        printf '\033[31m  ✗ 证书剩余 %d 天，需尽快续期\033[0m\n' "$DAYS_LEFT"
        FAIL=1
    else
        printf '\033[32m  ✓ 证书剩余 %d 天\033[0m\n' "$DAYS_LEFT"
    fi

    # 证书链完整性：缺中间证书时部分客户端（尤其移动端）会握手失败
    if echo | timeout 10 openssl s_client -servername "$domain" \
        -connect "${domain}:443" 2>&1 | grep -q 'Verify return code: 0'; then
        printf '\033[32m  ✓ 证书链验证通过\033[0m\n'
    else
        printf '\033[31m  ✗ 证书链不完整（应部署 fullchain 而非单证书）\033[0m\n'
        FAIL=1
    fi

    # 协议版本：TLS 1.0/1.1 已被主流浏览器弃用且不合规
    for proto in tls1 tls1_1; do
        if echo | timeout 5 openssl s_client -"$proto" -connect "${domain}:443" \
            >/dev/null 2>&1; then
            printf '\033[31m  ✗ 仍支持 %s，应仅保留 TLSv1.2 / TLSv1.3\033[0m\n' "$proto"
            FAIL=1
        fi
    done

    # HTTP 跳转
    CODE="$(curl -o /dev/null -sw '%{http_code}' --max-time 10 "http://${domain}/" 2>/dev/null)"
    if [[ "$CODE" == "301" || "$CODE" == "308" ]]; then
        printf '\033[32m  ✓ HTTP 已跳转 HTTPS（%s）\033[0m\n' "$CODE"
    else
        printf '\033[33m  ! HTTP 未跳转，返回 %s\033[0m\n' "${CODE:-无响应}"
    fi

    # HSTS
    if curl -sI --max-time 10 "https://${domain}/" 2>/dev/null \
        | grep -qi 'strict-transport-security'; then
        printf '\033[32m  ✓ 已启用 HSTS\033[0m\n'
    else
        printf '\033[33m  ! 未返回 HSTS 头\033[0m\n'
    fi
done

printf '\n'
if [[ "$FAIL" == "0" ]]; then
    printf '\033[32m全部检查通过\033[0m\n'
    exit 0
else
    printf '\033[31m存在需处理的证书问题\033[0m\n'
    exit 1
fi
