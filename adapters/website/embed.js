/**
 * Fangyu Defense — Generic website adapter (pure JS / no framework)
 * =================================================================
 *
 * 支持两种运行模式，自动检测：
 *
 * Hybrid 模式（推荐）
 * ------------------
 * 当上游已部署 CF Worker / Nginx-Lua / WordPress 插件时，服务端会在 HTML 中注入：
 *   window.__fy_server_ctx = { siteId, gatewayUrl, serverVerdict, serverToken, ... }
 *
 * SDK 检测到 __fy_server_ctx 后进入 hybrid 模式：
 *   - serverToken 携带进 /v2/decide，网关将服务端预判与浏览器指纹合并评分
 *   - 服务端已判为 hostile 的访客在 sessionStorage 缓存失效时由 SDK 兜底拦截
 *
 * Standalone 模式（降级）
 * -----------------------
 * 没有服务端层时，SDK 独立完成全部指纹收集与决策，行为与以前版本一致。
 *
 * 手动配置（仅 standalone 时需要）
 * --------------------------------
 *   window.FangyuConfig = {
 *     gatewayUrl: '...',
 *     siteId:     '...',
 *     failMode:   'open',   // 'open'（默认）或 'closed'
 *                           // 网关超时/不可达时：open=放行，closed=跳转屏蔽页
 *   }
 *
 * 降级链路
 * --------
 * 1. sessionStorage._fy_v (过期检查)  →  0ms 直接跳转（纯缓存，无网络）
 * 2. hybrid SDK（携带 serverToken）       →  两层合并评分
 * 3. SDK 加载失败 / 网关超时              →  按 failMode 决定：
 *      open   → 静默放行（默认）
 *      closed → 跳转 blockedUrl
 *
 * ⚠  Security note: App Secret 不再需要出现在前端。
 *    服务端层（CF Worker / Nginx-Lua）负责签名验证。
 *    standalone 模式下 SDK 直接调用 /v2/decide，无需签名。
 */

// =============================================================================
// Hybrid 模式 + Standalone 降级（自动检测，无需手动切换）
// 直接将此文件作为 SDK 的 onReady 入口，或在 standalone 时手动引入
// =============================================================================
/*
<script src="/assets/sd-sdk.min.js" defer></script>
<script>
(function () {
  // ── 第一层缓存兜底（任何模式下均有效）────────────────────────────────────
  // 存 {v, exp} 而非裸 verdict，过期即视为未命中，使 ttlSeconds 真正生效。
  var _c = null;
  try { _c = JSON.parse(sessionStorage.getItem('_fy_v') || 'null'); } catch (e) {}
  if (_c && _c.exp > Date.now() && _c.v === 'hostile') {
    var ctx0 = window.__fy_server_ctx || {};
    location.replace(ctx0.blockedUrl || '/blocked');
    return;
  }

  document.addEventListener('DOMContentLoaded', function () {
    // SDK 加载失败：按 failMode 决定
    if (typeof SdSdk === 'undefined') {
      var failCfg = window.FangyuConfig || window.__fy_server_ctx || {};
      if (failCfg.failMode === 'closed') {
        location.replace(failCfg.blockedUrl || '/blocked');
      }
      // failMode === 'open'（默认）：静默放行
      return;
    }

    // ── 自动检测运行模式 ──────────────────────────────────────────────────
    var serverCtx  = window.__fy_server_ctx;    // 服务端注入（hybrid 模式）
    var manualCfg  = window.FangyuConfig;       // 手动配置（standalone 模式）

    var cfg = serverCtx || manualCfg || {};
    if (!cfg.gatewayUrl || !cfg.siteId) {
      console.warn('[fangyu] 未找到配置，SDK 跳过初始化');
      return;
    }

    var isHybrid     = !!serverCtx;
    var blockedUrl   = cfg.blockedUrl   || '/blocked';
    var challengeUrl = cfg.challengeUrl || '/challenge';
    // failMode：hybrid 模式由服务端 ctx 携带（扩展字段），standalone 由 FangyuConfig 配置
    var failMode     = cfg.failMode || 'open';

    // hybrid 模式：服务端已判为 hostile，此处作为兜底（正常应在服务端已拦截）
    if (isHybrid && serverCtx.serverVerdict === 'hostile') {
      sessionStorage.setItem('_fy_v', JSON.stringify({ v: 'hostile', exp: Date.now() + 300000 }));
      location.replace(blockedUrl);
      return;
    }

    SdSdk.protect({
      gatewayUrl:      cfg.gatewayUrl,
      siteId:          cfg.siteId,
      // hybrid 模式携带服务端 token，网关合并两层评分
      serverToken:     isHybrid ? serverCtx.serverToken : undefined,
      autoApply:       false,
      collectBehavior: true,
      onDecision: function (d) {
        sessionStorage.setItem('_fy_v', JSON.stringify({
          v: d.verdict, exp: Date.now() + (d.ttlSeconds || 300) * 1000
        }));

        if (d.mechanism === 'redirect') {
          location.replace(
            (d.target && d.target.url) ? d.target.url : blockedUrl
          );
        } else if (d.mechanism === 'challenge') {
          location.replace(
            challengeUrl + '?next=' + encodeURIComponent(location.href)
          );
        } else if (d.mechanism === 'deny') {
          document.documentElement.innerHTML =
            '<body style="font:sans-serif;text-align:center;padding:80px">' +
            '<h1>403</h1><p>Access Denied</p></body>';
        }
        // mechanism === 'pass' → 什么都不做，用户正常浏览
      },
      onError: function () {
        // 网关超时 / 网络不可达 / SDK 内部错误
        if (failMode === 'closed') {
          location.replace(blockedUrl);
        }
        // failMode === 'open'（默认）：静默放行，不影响正常用户
      }
    });
  });
}());
</script>
*/
// 放在 <head> 底部，SDK defer 加载不阻塞渲染
// =============================================================================
/*
<!-- 第一层：读缓存，已知恶意 0ms 直接跳（放在 <head> 最顶部，同步执行） -->
<script>
  (function () {
    var _c = null;
    try { _c = JSON.parse(sessionStorage.getItem('_fy_v') || 'null'); } catch (e) {}
    if (_c && _c.exp > Date.now() && _c.v === 'hostile') location.replace('/blocked');
  })();
</script>

<!-- SDK 异步加载，不阻塞渲染 -->
<script src="/assets/sd-sdk.min.js" defer></script>
<script>
  window.FangyuConfig = {
    gatewayUrl:      'https://YOUR_GATEWAY_URL',
    siteId:          'site_xxxxxxxx',
    // 可疑/敌对时的跳转目标（留空则由服务端 disposition 决定）
    redirectBlocked: '/blocked',        // hostile → 跳转到屏蔽页
    challengeUrl:    '/challenge',      // suspect → 跳转到验证页
  };
</script>
<script>
  document.addEventListener('DOMContentLoaded', function () {
    SdSdk.protect({
      gatewayUrl:      FangyuConfig.gatewayUrl,
      siteId:          FangyuConfig.siteId,
      autoApply:       false,           // 手动处理，精确控制跳转时机
      collectBehavior: true,
      onDecision: function (decision) {
        // 缓存本次判定结果，下次访问第一层直接拦截
        sessionStorage.setItem('_fy_v', decision.verdict);

        if (decision.mechanism === 'redirect') {
          // 服务端指定了跳转 URL 时，使用 replace 不留历史记录
          location.replace(decision.target && decision.target.url
            ? decision.target.url
            : FangyuConfig.redirectBlocked);

        } else if (decision.mechanism === 'challenge') {
          // 跳转到验证页，携带原始 URL 用于验证通过后回跳
          location.replace(
            FangyuConfig.challengeUrl +
            '?next=' + encodeURIComponent(location.href)
          );

        } else if (decision.mechanism === 'serve_alt') {
          // 投放替代内容：整页替换为服务端下发的 pageContent
          if (decision.pageContent) {
            document.documentElement.innerHTML = decision.pageContent;
          } else {
            // 资源被禁用/删除时 pageContent 为空，退化为阻断而非放行
            document.documentElement.innerHTML =
              '<body style="font-family:sans-serif;text-align:center;padding:80px">' +
              '<h1>403</h1><p>Access Denied</p></body>';
          }

        } else if (decision.mechanism === 'deny') {
          // 直接替换当前页面内容，不跳转（无 URL 变化，Bot 更难发现被拦）
          document.documentElement.innerHTML =
            '<body style="font-family:sans-serif;text-align:center;padding:80px">' +
            '<h1>403</h1><p>Access Denied</p></body>';

        } else if (decision.mechanism === 'not_found') {
          // 伪装成 404，不暴露「被识别」这一事实
          document.documentElement.innerHTML =
            '<body style="font-family:sans-serif;text-align:center;padding:80px">' +
            '<h1>404</h1><p>Not Found</p></body>';

        } else if (decision.mechanism !== 'pass') {
          // 未知机制：留下日志，避免后端新增机制而接入代码未同步时无声放行
          console.warn('[fangyu] unknown mechanism:', decision.mechanism);
        }
        // mechanism === 'pass' 时什么都不做，用户正常浏览
      }
    });
  });
</script>
*/

// =============================================================================
// 接入方式 B：内容隐藏模式（更严格，防止 Bot 在判定完成前抓取内容）
// 适合商品详情页、定价页等高价值页面
// =============================================================================
/*
<style id="_fy_hide">
  body > * { visibility: hidden !important; }
</style>
<script>
  // 超时保护：300ms 内未完成判定则强制显示，避免网络差时白屏
  var _fyTimeout = setTimeout(function () {
    var s = document.getElementById('_fy_hide');
    if (s) s.remove();
  }, 300);
</script>

<script src="/assets/sd-sdk.min.js" defer></script>
<script>
  document.addEventListener('DOMContentLoaded', function () {
    SdSdk.protect({
      gatewayUrl:      'https://YOUR_GATEWAY_URL',
      siteId:          'site_xxxxxxxx',
      autoApply:       false,
      collectBehavior: true,
      onDecision: function (decision) {
        clearTimeout(_fyTimeout);
        sessionStorage.setItem('_fy_v', decision.verdict);

        if (decision.verdict === 'hostile' || decision.mechanism === 'redirect') {
          location.replace('/blocked');
        } else if (decision.mechanism === 'challenge') {
          location.replace('/challenge?next=' + encodeURIComponent(location.href));
        } else {
          // 正常访客：移除隐藏样式，内容显现
          var s = document.getElementById('_fy_hide');
          if (s) s.remove();
        }
      }
    });
  });
</script>
*/

// =============================================================================
// 接入方式 C：仅保护特定操作（如结账、加购）
// 页面正常显示，仅在用户触发关键动作时触发判定
// =============================================================================
/*
<script src="/assets/sd-sdk.min.js" defer></script>
<script>
  var _fySDK = new SdSdk({
    gatewayUrl:      'https://YOUR_GATEWAY_URL',
    siteId:          'site_xxxxxxxx',
    autoApply:       false,
    collectBehavior: true,   // 后台持续收集行为信号，不触发判定
  });
  _fySDK.init();  // 预热连接，减少后续 decide() 延迟

  // 在结账按钮点击时才触发判定
  document.addEventListener('click', async function (e) {
    var btn = e.target.closest('[data-fangyu-gate]');
    if (!btn) return;

    e.preventDefault();
    e.stopPropagation();

    btn.disabled = true;
    try {
      var decision = await _fySDK.decide();
      sessionStorage.setItem('_fy_v', decision.verdict);

      if (decision.verdict === 'hostile') {
        location.replace('/blocked');
      } else if (decision.mechanism === 'challenge') {
        location.replace('/challenge?next=' + encodeURIComponent(location.href));
      } else {
        btn.disabled = false;
        btn.click();  // 重新触发原始点击
      }
    } catch (err) {
      // 判定失败（网络异常等）：开放通过，不影响正常用户
      btn.disabled = false;
      btn.click();
    }
  });
</script>

<!-- 在需要保护的按钮上加 data-fangyu-gate 属性即可 -->
<!-- <button data-fangyu-gate>立即购买</button> -->
*/

// ── Disposition values returned by sdk.decide() ──────────────────────────────
//
//   verdict:   'trusted'  — 正常访客
//   verdict:   'suspect'  — 可疑，通常触发验证
//   verdict:   'hostile'  — 敌对，通常直接跳转屏蔽页
//
//   mechanism: 'pass'       — 放行，无需处理
//   mechanism: 'serve_alt'  — 投放替代页面，pageContent 为下发内容
//   mechanism: 'redirect'   — 跳转，target.url 为服务端指定目标
//   mechanism: 'challenge'  — 触发人机验证
//   mechanism: 'deny'       — 拒绝访问（替换页面内容或跳转）
//   mechanism: 'not_found'  — 伪装成 404
//   mechanism: 'status_only' — 仅记录状态码，不实际阻断（用于 Nginx/CF 适配器）
