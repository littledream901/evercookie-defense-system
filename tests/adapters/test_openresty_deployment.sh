#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# Fangyu Defense — OpenResty 部署测试脚本
# ═══════════════════════════════════════════════════════════════════════
# 用途: 自动化测试 OpenResty Lua 适配器的部署状态
# 环境: Linux / macOS (在 1Panel 服务器上运行)
# 依赖: curl, grep, openresty
# ═══════════════════════════════════════════════════════════════════════

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置项（根据实际情况修改）
OPENRESTY_PREFIX="${OPENRESTY_PREFIX:-/opt/1panel/apps/openresty/openresty}"
LUA_SCRIPT_PATH="${OPENRESTY_PREFIX}/conf/lua/fangyu/defense.lua"
NGINX_CONF="${OPENRESTY_PREFIX}/conf/nginx.conf"
ERROR_LOG="${OPENRESTY_PREFIX}/logs/error.log"
TEST_URL="${TEST_URL:-http://localhost}"
GATEWAY_URL="${GATEWAY_URL:-}"  # 留空表示从配置文件读取

# ═══════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        log_success "$1 已安装"
        return 0
    else
        log_error "$1 未安装，请先安装"
        return 1
    fi
}

# ═══════════════════════════════════════════════════════════════════════
# 测试函数
# ═══════════════════════════════════════════════════════════════════════

test_1_prerequisites() {
    log_info "【测试 1】检查前置条件"
    
    local pass=0
    
    # 检查 OpenResty
    if command -v openresty &> /dev/null; then
        local version=$(openresty -v 2>&1 | grep -oP 'openresty/\K[0-9.]+')
        log_success "OpenResty 版本: $version"
        
        # 检查版本号 >= 1.21
        local major=$(echo "$version" | cut -d. -f1)
        local minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -gt 1 ] || ([ "$major" -eq 1 ] && [ "$minor" -ge 21 ]); then
            log_success "版本满足要求 (>= 1.21)"
        else
            log_error "版本过低，建议升级到 1.21+"
            ((pass++))
        fi
    else
        log_error "OpenResty 未安装"
        ((pass++))
    fi
    
    # 检查 curl
    check_command curl || ((pass++))
    
    return $pass
}

test_2_file_structure() {
    log_info "【测试 2】检查文件结构"
    
    local pass=0
    
    # 检查 Lua 脚本
    if [ -f "$LUA_SCRIPT_PATH" ]; then
        log_success "Lua 脚本存在: $LUA_SCRIPT_PATH"
        
        # 检查文件权限
        local perms=$(stat -c "%a" "$LUA_SCRIPT_PATH" 2>/dev/null || stat -f "%Lp" "$LUA_SCRIPT_PATH" 2>/dev/null)
        if [ "$perms" = "644" ] || [ "$perms" = "444" ]; then
            log_success "文件权限正确: $perms"
        else
            log_warning "文件权限: $perms (建议 644)"
        fi
    else
        log_error "Lua 脚本不存在: $LUA_SCRIPT_PATH"
        ((pass++))
    fi
    
    # 检查 Nginx 配置
    if [ -f "$NGINX_CONF" ]; then
        log_success "Nginx 配置存在: $NGINX_CONF"
    else
        log_error "Nginx 配置不存在: $NGINX_CONF"
        ((pass++))
    fi
    
    return $pass
}

test_3_lua_modules() {
    log_info "【测试 3】检查 Lua 模块依赖"
    
    local pass=0
    local lualib="${OPENRESTY_PREFIX}/lualib/resty"
    
    # 检查必需模块
    local modules=("http.lua" "cjson.so")
    for mod in "${modules[@]}"; do
        if find "$lualib" -name "$mod" | grep -q .; then
            log_success "模块存在: $mod"
        else
            log_error "模块缺失: $mod"
            ((pass++))
        fi
    done
    
    # 检查 HMAC 模块（两种可能）
    if find "$lualib" -name "hmac.lua" -o -name "hmac" -type d | grep -q .; then
        log_success "HMAC 模块存在 (lua-resty-hmac)"
    elif find "$lualib" -path "*/openssl/hmac.lua" | grep -q .; then
        log_success "HMAC 模块存在 (resty.openssl.hmac)"
    else
        log_error "HMAC 模块缺失，需要安装 lua-resty-hmac 或 lua-resty-openssl"
        ((pass++))
    fi
    
    return $pass
}

test_4_nginx_config() {
    log_info "【测试 4】检查 Nginx 配置"
    
    local pass=0
    
    # 检查是否引用了 defense.lua
    if grep -q "access_by_lua_file.*defense.lua" "$NGINX_CONF"; then
        log_success "配置中包含 access_by_lua_file"
    else
        log_warning "配置中未找到 access_by_lua_file 指令"
    fi
    
    # 检查是否配置了变量
    local vars=("fangyu_gateway_url" "fangyu_site_id" "fangyu_app_secret")
    for var in "${vars[@]}"; do
        if grep -q "set \$$var" "$NGINX_CONF"; then
            log_success "配置变量存在: \$$var"
        else
            log_warning "配置变量缺失: \$$var"
            ((pass++))
        fi
    done
    
    # 检查 lua_code_cache
    if grep -q "lua_code_cache.*on" "$NGINX_CONF"; then
        log_success "lua_code_cache 已开启"
    else
        log_warning "lua_code_cache 未开启（生产环境必须开启）"
    fi
    
    # 语法检查
    log_info "执行 Nginx 配置语法检查..."
    if openresty -t &> /tmp/nginx_test.log; then
        log_success "Nginx 配置语法正确"
    else
        log_error "Nginx 配置语法错误:"
        cat /tmp/nginx_test.log
        ((pass++))
    fi
    
    return $pass
}

test_5_process_status() {
    log_info "【测试 5】检查进程状态"
    
    local pass=0
    
    # 检查 OpenResty 是否运行
    if pgrep -f "nginx: master process" > /dev/null; then
        log_success "OpenResty 主进程运行中"
        
        # 检查工作进程数
        local workers=$(pgrep -f "nginx: worker process" | wc -l)
        log_info "工作进程数: $workers"
    else
        log_error "OpenResty 未运行"
        ((pass++))
    fi
    
    return $pass
}

test_6_error_logs() {
    log_info "【测试 6】检查错误日志"
    
    local pass=0
    
    if [ ! -f "$ERROR_LOG" ]; then
        log_warning "错误日志文件不存在: $ERROR_LOG"
        return 0
    fi
    
    # 检查最近 100 行日志
    log_info "分析最近的错误日志..."
    
    # 查找 Lua 错误
    local lua_errors=$(tail -n 100 "$ERROR_LOG" | grep -iE "lua|pcall" | wc -l)
    if [ "$lua_errors" -gt 0 ]; then
        log_warning "发现 $lua_errors 条 Lua 相关错误"
        tail -n 100 "$ERROR_LOG" | grep -iE "lua|pcall" | tail -n 3
        ((pass++))
    else
        log_success "无 Lua 错误"
    fi
    
    # 查找 Fangyu 相关日志
    local fangyu_logs=$(tail -n 100 "$ERROR_LOG" | grep -i "fangyu" | wc -l)
    if [ "$fangyu_logs" -gt 0 ]; then
        log_info "发现 $fangyu_logs 条 Fangyu 相关日志"
        tail -n 100 "$ERROR_LOG" | grep -i "fangyu" | tail -n 3
    fi
    
    # 查找模块加载失败
    if tail -n 100 "$ERROR_LOG" | grep -q "module.*not found"; then
        log_error "发现模块加载失败"
        tail -n 100 "$ERROR_LOG" | grep "module.*not found" | tail -n 3
        ((pass++))
    fi
    
    return $pass
}

test_7_http_request() {
    log_info "【测试 7】HTTP 请求测试"
    
    local pass=0
    
    # 基础连通性测试
    log_info "测试 URL: $TEST_URL"
    
    if curl -s -o /dev/null -w "%{http_code}" "$TEST_URL" | grep -qE "^(200|301|302)$"; then
        log_success "HTTP 请求成功"
    else
        local code=$(curl -s -o /dev/null -w "%{http_code}" "$TEST_URL")
        log_error "HTTP 请求失败，状态码: $code"
        ((pass++))
    fi
    
    # 检查响应头
    log_info "检查响应头..."
    local headers=$(curl -s -I "$TEST_URL")
    
    # 检查是否有 Server 头（可能被隐藏）
    if echo "$headers" | grep -q "Server:"; then
        local server=$(echo "$headers" | grep "Server:" | cut -d: -f2 | xargs)
        log_info "Server: $server"
    fi
    
    return $pass
}

test_8_sdk_injection() {
    log_info "【测试 8】SDK 注入测试"
    
    local pass=0
    
    # 获取 HTML 响应
    local html=$(curl -s "$TEST_URL")
    
    # 检查是否包含 SDK 上下文
    if echo "$html" | grep -q "window.__fy_server_ctx"; then
        log_success "检测到 SDK 上下文对象"
    else
        log_warning "未检测到 SDK 上下文对象（可能未注入或非 HTML 响应）"
    fi
    
    # 检查是否包含 SDK 脚本
    if echo "$html" | grep -q "fangyu-sdk.min.js"; then
        log_success "检测到 SDK 脚本标签"
    else
        log_warning "未检测到 SDK 脚本标签"
    fi
    
    # 检查是否包含 sessionStorage 逻辑
    if echo "$html" | grep -q "sessionStorage.getItem.*_fy_v"; then
        log_success "检测到客户端缓存逻辑"
    else
        log_warning "未检测到客户端缓存逻辑"
    fi
    
    return $pass
}

test_9_gateway_connectivity() {
    log_info "【测试 9】Gateway 连通性测试"
    
    local pass=0
    
    # 从配置文件提取 Gateway URL
    if [ -z "$GATEWAY_URL" ]; then
        GATEWAY_URL=$(grep -oP 'set \$fangyu_gateway_url\s+"\K[^"]+' "$NGINX_CONF" | head -1)
    fi
    
    if [ -z "$GATEWAY_URL" ]; then
        log_warning "未配置 Gateway URL，跳过测试"
        return 0
    fi
    
    log_info "Gateway URL: $GATEWAY_URL"
    
    # 测试 Gateway 健康检查（如果有）
    if curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/healthz" | grep -q "200"; then
        log_success "Gateway 健康检查通过"
    elif curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/health" | grep -q "200"; then
        log_success "Gateway 健康检查通过"
    else
        log_warning "Gateway 健康检查失败（可能端点不存在或网络不通）"
        ((pass++))
    fi
    
    return $pass
}

test_10_signature_parity() {
    log_info "【测试 10】签名算法一致性测试"
    
    local pass=0
    
    # 创建临时 Lua 测试脚本
    local test_script="/tmp/fangyu_sign_test.lua"
    
    cat > "$test_script" << 'LUAEOF'
-- 复制 defense.lua 的核心签名函数进行单元测试
package.path = package.path .. ";/opt/1panel/apps/openresty/openresty/lualib/?.lua"

local cjson = require "cjson.safe"

-- HMAC 函数（简化版，使用 openssl 命令行）
local function compute_hmac(secret, message)
    local cmd = string.format('echo -n "%s" | openssl dgst -sha256 -hmac "%s" | cut -d" " -f2',
                               message:gsub('"', '\\"'), secret:gsub('"', '\\"'))
    local handle = io.popen(cmd)
    local result = handle:read("*a"):gsub("%s+", "")
    handle:close()
    return result
end

-- URL 编码函数
local function encode_component(s)
    s = tostring(s)
    return (s:gsub("[^A-Za-z0-9%-_.!~*'()]", function(c)
        return string.format("%%%02X", string.byte(c))
    end))
end

-- 构建签名载荷
local function build_payload(params)
    local keys = {}
    for k in pairs(params) do keys[#keys+1] = tostring(k) end
    table.sort(keys)
    
    local parts = {}
    for _, k in ipairs(keys) do
        if k ~= "sign" then
            local v = params[k]
            if v ~= nil and v ~= "" then
                local val = type(v) == "table" and cjson.encode(v) or tostring(v)
                parts[#parts+1] = encode_component(k) .. "=" .. encode_component(val)
            end
        end
    end
    return table.concat(parts, "&")
end

-- 测试用例（与 Python 版本对齐）
local test_cases = {
    {
        params = { timestamp = 1700000000, nonce = "aaaa", context = {ip = "1.1.1.1"} },
        secret = "test_secret",
        expected_payload = 'context=%7B%22ip%22%3A%221.1.1.1%22%7D&nonce=aaaa&timestamp=1700000000'
    }
}

local all_pass = true
for i, tc in ipairs(test_cases) do
    local payload = build_payload(tc.params)
    local sign = compute_hmac(tc.secret, payload)
    
    if payload == tc.expected_payload then
        print(string.format("[✓] 测试用例 %d: Payload 匹配", i))
    else
        print(string.format("[✗] 测试用例 %d: Payload 不匹配", i))
        print("  期望: " .. tc.expected_payload)
        print("  实际: " .. payload)
        all_pass = false
    end
    
    print(string.format("  签名: %s", sign))
end

os.exit(all_pass and 0 or 1)
LUAEOF
    
    # 运行测试
    if lua "$test_script" 2>/dev/null; then
        log_success "签名算法测试通过"
    else
        log_warning "签名算法测试失败（需要进一步排查）"
        ((pass++))
    fi
    
    rm -f "$test_script"
    return $pass
}

# ═══════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════

main() {
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  Fangyu Defense — OpenResty 部署测试${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    local total_failures=0
    
    test_1_prerequisites || ((total_failures+=$?))
    echo ""
    
    test_2_file_structure || ((total_failures+=$?))
    echo ""
    
    test_3_lua_modules || ((total_failures+=$?))
    echo ""
    
    test_4_nginx_config || ((total_failures+=$?))
    echo ""
    
    test_5_process_status || ((total_failures+=$?))
    echo ""
    
    test_6_error_logs || ((total_failures+=$?))
    echo ""
    
    test_7_http_request || ((total_failures+=$?))
    echo ""
    
    test_8_sdk_injection || ((total_failures+=$?))
    echo ""
    
    test_9_gateway_connectivity || ((total_failures+=$?))
    echo ""
    
    test_10_signature_parity || ((total_failures+=$?))
    echo ""
    
    # 总结
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    if [ "$total_failures" -eq 0 ]; then
        echo -e "${GREEN}✓ 所有测试通过！部署状态良好${NC}"
        exit 0
    else
        echo -e "${RED}✗ 发现 $total_failures 个问题，请根据上述提示进行修复${NC}"
        echo ""
        log_info "常见修复方法:"
        echo "  1. 安装缺失模块: 参考 docs/deployment/OPENRESTY_DEPLOYMENT.md"
        echo "  2. 修复配置错误: openresty -t 查看详细信息"
        echo "  3. 检查日志: tail -f $ERROR_LOG"
        echo "  4. 重启服务: systemctl restart openresty"
        exit 1
    fi
}

# 运行主函数
main "$@"
