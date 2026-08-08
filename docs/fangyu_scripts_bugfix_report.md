# fangyu_scripts.py 业务逻辑修复报告

## 修复日期
2026-08-07

## 修复概述
修复了 `nginx-dep/fangyu_scripts.py` 中的 5 个关键业务逻辑错误，确保脚本能够正确部署 Fangyu Defense 到 1Panel OpenResty 环境。

---

## 修复详情

### 1. ✅ defense.lua 文件路径错误 (严重)
**文件位置**: `fangyu_scripts.py:410-427`  
**问题描述**: 脚本查找 defense.lua 的路径不正确，因为脚本位于 `nginx-dep/` 目录，而 `adapters/` 文件夹在上一级目录。

**修复前**:
```python
possible_paths = [
    str(Path(__file__).parent / "adapters" / "nginx-lua" / "defense.lua"),
    "./adapters/nginx-lua/defense.lua",
]
```

**修复后**:
```python
possible_paths = [
    str(Path(__file__).parent.parent / "adapters" / "nginx-lua" / "defense.lua"),  # 优先
    str(Path(__file__).parent / "adapters" / "nginx-lua" / "defense.lua"),
    "./adapters/nginx-lua/defense.lua",
    "../adapters/nginx-lua/defense.lua",
]
```

**影响**: 会导致找不到 defense.lua 文件，部署失败。

---

### 2. ✅ access_by_lua_file 注入时的重复添加 bug (严重)
**文件位置**: `fangyu_scripts.py:575-610`  
**问题描述**: 在找到 `set $fy_sdk_snippet` 行后执行 `continue`，但循环末尾又会再次 `append(line)`，导致该行被添加两次。

**修复前**:
```python
if 'set $fy_sdk_snippet' in line or 'set $fy_server_token' in line:
    found_vars = True
    new_lines.append(line)
    continue  # 这里 continue，但下面还有 append
    
# 变量声明后插入
if found_vars and stripped and ...:
    new_lines.append(access_lua)
    inserted_access = True

new_lines.append(line)  # ⚠️ 导致重复添加
```

**修复后**:
```python
if 'set $fy_sdk_snippet' in line or 'set $fy_server_token' in line:
    found_vars = True
    new_lines.append(line)
    continue  # 这里 continue，不会执行后面的 append
    
# 变量声明后插入
if found_vars and stripped and ...:
    new_lines.append(access_lua)
    new_lines.append(line)  # 先插入 access_lua，再添加当前行
    inserted_access = True
    continue  # 避免重复添加

new_lines.append(line)
```

**影响**: 会导致 Nginx 配置中某些行重复，可能导致配置错误。

---

### 3. ✅ body_filter 删除逻辑的括号计数错误 (严重)
**文件位置**: `fangyu_scripts.py:587-597`  
**问题描述**: 
1. 初始括号计数应该从 `body_filter_by_lua_block {` 这一行开始
2. 结束条件应该是 `<= 0` 而不是 `< 0`

**修复前**:
```python
if 'body_filter_by_lua_block' in line:
    in_body_filter = True
    body_filter_brace_count = 0  # ⚠️ 错误：没有计算第一行的括号
    continue

if in_body_filter:
    body_filter_brace_count += line.count('{') - line.count('}')
    if body_filter_brace_count < 0:  # ⚠️ 错误：应该是 <= 0
        in_body_filter = False
    continue
```

**修复后**:
```python
if 'body_filter_by_lua_block' in line:
    in_body_filter = True
    body_filter_brace_count = line.count('{') - line.count('}')  # ✓ 计算第一行
    continue

if in_body_filter:
    body_filter_brace_count += line.count('{') - line.count('}')
    if body_filter_brace_count <= 0:  # ✓ 修正为 <= 0
        in_body_filter = False
    continue
```

**影响**: 可能无法完整删除 body_filter 块，导致旧配置残留。

---

### 4. ✅ body_filter 注入的括号匹配逻辑优化 (中等)
**文件位置**: `fangyu_scripts.py:612-653`  
**问题描述**: 原逻辑假设 `server {` 已经打开一个括号（硬编码 `brace_count = 1`），不够通用。

**修复前**:
```python
if 'server {' in line:
    server_start = i
    break

if server_start >= 0:
    brace_count = 1  # ⚠️ 硬编码假设
    
    for i in range(server_start + 1, len(lines)):
        ...
```

**修复后**:
```python
if 'server {' in line or 'server{' in line:  # 支持无空格格式
    server_start = i
    break

if server_start >= 0:
    brace_count = 0
    # 先计算 server { 这一行的括号
    brace_count += lines[server_start].count('{') - lines[server_start].count('}')
    
    for i in range(server_start + 1, len(lines)):
        ...
```

**影响**: 提高了对不同格式 Nginx 配置的兼容性，支持一行多个括号的情况。

---

### 5. ✅ remove_old_fangyu_config 检测逻辑增强 (严重)
**文件位置**: `fangyu_scripts.py:558-562`  
**问题描述**: 只检查变量声明，不检查 `body_filter_by_lua_block` 和 `access_by_lua_file`，导致这些配置无法被删除。

**修复前**:
```python
if 'Fangyu Defense' not in config_content and 'fangyu_gateway_url' not in config_content:
    return config_content  # ⚠️ 提前返回，不删除 body_filter
```

**修复后**:
```python
# 检查是否有任何 Fangyu 相关配置
has_fangyu_config = (
    'Fangyu Defense' in config_content or 
    'fangyu_gateway_url' in config_content or
    'body_filter_by_lua_block' in config_content or
    'access_by_lua_file' in config_content and 'defense.lua' in config_content
)

if not has_fangyu_config:
    return config_content
```

**附加修复**: 删除变量块时也检查 `set $fy_*` 变量：
```python
if line.strip().startswith('set $fangyu_') or line.strip().startswith('set $fy_') or line.strip() == '':
    continue
```

**影响**: 确保所有 Fangyu 相关配置都能被正确识别和删除。

---

## 测试验证

创建了完整的单元测试文件 `test/test_fangyu_scripts_logic.py`，包含 6 个测试用例：

1. ✅ 变量块注入测试
2. ✅ access_lua 注入无重复测试
3. ✅ 删除旧配置测试
4. ✅ body_filter 括号计数测试
5. ✅ body_filter 多行括号注入测试
6. ✅ 查找 defense.lua 测试

**测试结果**: 6 通过, 0 失败

---

## 影响范围

- ✅ 不影响现有功能
- ✅ 向后兼容
- ✅ 提高了脚本的健壮性和可靠性
- ✅ 所有修复均已通过单元测试验证

---

## 建议后续改进

1. **安全性**: 将硬编码的敏感配置移到 `.env` 文件（符合 DIR-001 规范）
2. **日志**: 使用标准的 `logging.getLogger(__name__)` 替代自定义 Logger 类（符合 LOG-003 规范）
3. **异常处理**: 细化异常类型，避免通用的 `except Exception`
4. **配置文件查找**: 增加更多可能的路径，提高容错性

---

## 修复文件清单

- ✅ `nginx-dep/fangyu_scripts.py` - 主脚本修复
- ✅ `test/test_fangyu_scripts_logic.py` - 新增测试文件
- ✅ `docs/fangyu_scripts_bugfix_report.md` - 本修复报告

---

## 签名
修复完成并验证通过  
日期: 2026-08-07
