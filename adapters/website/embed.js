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
 *
 * ⚠  时序：同步阻塞只适用于 standalone
 * -------------------------------------
 * 本文件的方式 A / A' 是 **standalone**（无服务端层，SDK 是唯一防线）的写法：
 * 放在 `<head>` 内尽量靠前，script **不加 defer**，用 `SdSdk.guard()`。
 * 此时 SDK 判定是唯一的拦截机会，跳转命中率也高（落地页场景），
 * 同步阻塞换来的「命中跳转的访客看不到正文」是实打实的收益。
 *
 * **hybrid 模式（带 CF Worker / nginx-lua / WordPress 服务端层）不要这样做。**
 * 那三个适配器只在服务端判 pass 时才注入 SDK，能执行到脚本的访客都已通过第一层，
 * 客户端层的跳转命中率按设计就低；且 HTML 已完整下发，同步阻塞连「防正文泄露」
 * 都做不到。它们保持 defer + DOMContentLoaded + `protect()`。
 *
 * 无论哪种模式，「缓存命中已知 hostile 直接跳」那一小段都值得同步执行——
 * 它不依赖 SDK、不发请求，成本接近零。
 */

// =============================================================================
// 接入方式 A（standalone 推荐）：head 同步接入，跳转优先于渲染
//
// 适用前提：**没有服务端层**，SDK 是唯一防线。典型场景是广告落地页、短链页，
// 跳转本身就是主要业务逻辑，命中率高，同步阻塞的收益明确。
//
// 有 CF Worker / nginx-lua / WordPress 服务端层时不要用这个写法，
// 那三个适配器自带 defer 版本的注入逻辑（原因见文件头注释）。
//
// 全部放在 <head> 内尽量靠前的位置。SdSdk.guard() 内部会：
//   1. 同步读决策缓存 → 命中即跳转（零网络，body 尚未解析）
//   2. 未命中 → 发起决策请求，命中跳转条件时先 window.stop() 再跳
//   3. 判为放行 → 不做任何干预，页面正常渲染
// =============================================================================
/*
<script src="/assets/sd-sdk.min.js"></script>
<script>
(function () {
  var cfg = window.FangyuConfig || {};

  // SDK 加载失败：按 failMode 决定（open=放行，closed=跳屏蔽页）
  if (typeof SdSdk === 'undefined') {
    if (cfg.failMode === 'closed') {
      location.replace(cfg.blockedUrl || '/blocked');
    }
    return;
  }

  // 字段名以 client-sdk/src/config.ts 的 SdkConfig 为准
  if (!cfg.apiBase || !cfg.apiKey || !cfg.appId) {
    console.warn('[fangyu] 未找到配置，SDK 跳过初始化');
    return;
  }

  var blockedUrl = cfg.blockedUrl || '/blocked';
  var failMode   = cfg.failMode   || 'open';

  var outcome = SdSdk.guard({
    apiBase: cfg.apiBase,
    apiKey:  cfg.apiKey,
    appId:   cfg.appId,
    // 高价值页面可开启：判定完成前隐藏正文，hideTimeout 兜底防白屏
    // hideUntilDecided: true,
  });

  // 命中缓存时 outcome.cached 为 true，处置已同步执行完毕
  if (!outcome.pending) return;

  outcome.pending.catch(function () {
    // 网关超时 / 网络不可达 / SDK 内部错误
    if (failMode === 'closed') {
      location.replace(blockedUrl);
    }
    // failMode === 'open'（默认）：静默放行，不影响正常用户
  });
}());
</script>
*/
// =============================================================================
// 接入方式 A'：自行处理处置（autoApply: false）
//
// 需要自定义跳转目标或落地行为时使用。注意仍放 <head> 内、不加 defer。
// =============================================================================
/*
<script>
  window.FangyuConfig = {
    apiBase: 'https://YOUR_GATEWAY_URL',
    apiKey:  'site_xxxxxxxx',   // 走 X-App-Key，可公开
    appId:   123,               // 数字主键，非 site_xxx 字符串
    // 可疑/敌对时的跳转目标（留空则由服务端 disposition 决定）
    redirectBlocked: '/blocked',
    challengeUrl:    '/challenge',
  };
</script>
<script src="/assets/sd-sdk.min.js"></script>
<script>
(function () {
  var cfg = window.FangyuConfig;

  var outcome = SdSdk.guard({
    apiBase:   cfg.apiBase,
    apiKey:    cfg.apiKey,
    appId:     cfg.appId,
    autoApply: false,            // 手动处理，精确控制跳转时机
  });

  if (!outcome.pending) return;

  outcome.pending.then(function (result) {
    var decision = result.decision;

    if (decision.mechanism === 'redirect') {
      // 先掐掉在途请求，再跳；replace 不留历史记录
      if (window.stop) { try { window.stop(); } catch (e) {} }
      location.replace(decision.targetUrl || cfg.redirectBlocked);

    } else if (decision.mechanism === 'challenge') {
      // 跳转到验证页，携带原始 URL 用于验证通过后回跳
      location.replace(
        cfg.challengeUrl + '?next=' + encodeURIComponent(location.href)
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
  }).catch(function () {
    // 网关异常：静默放行
  });
}());
</script>
*/

// =============================================================================
// 接入方式 B：内容隐藏模式（更严格，防止 Bot 在判定完成前抓取内容）
// 适合商品详情页、定价页等高价值页面
//
// 隐藏与超时兜底已内置在 SDK 里，无需手写 <style> + setTimeout：
//   hideUntilDecided: true  判定完成前隐藏 body
//   hideTimeout: 300        到点强制显示，避免网络差时白屏
// =============================================================================
/*
<script src="/assets/sd-sdk.min.js"></script>
<script>
  SdSdk.guard({
    apiBase: 'https://YOUR_GATEWAY_URL',
    apiKey:  'site_xxxxxxxx',
    appId:   123,
    hideUntilDecided: true,
    hideTimeout:      300,
  });
</script>
*/

// =============================================================================
// 接入方式 C：仅保护特定操作（如结账、加购）
// 页面正常显示，仅在用户触发关键动作时触发判定
// =============================================================================
/*
<!-- 本方式不拦截页面渲染，因此可以 defer 加载 -->
<script src="/assets/sd-sdk.min.js" defer></script>
<script>
  var _fySDK;
  document.addEventListener('DOMContentLoaded', function () {
    _fySDK = new SdSdk({
      apiBase:         'https://YOUR_GATEWAY_URL',
      apiKey:          'site_xxxxxxxx',
      appId:           123,
      autoApply:       false,
      collectBehavior: true,   // 后台持续收集行为信号，不触发判定
    });
    _fySDK.init();  // 预热连接与指纹缓存，减少后续 decide() 延迟
  });

  // 在结账按钮点击时才触发判定
  document.addEventListener('click', async function (e) {
    var btn = e.target.closest('[data-fangyu-gate]');
    if (!btn || !_fySDK) return;

    e.preventDefault();
    e.stopPropagation();

    btn.disabled = true;
    try {
      // decide() 返回 {decision, applied}，处置字段在 decision 上
      var decision = (await _fySDK.decide()).decision;

      if (decision.verdict === 'hostile' || decision.mechanism === 'redirect') {
        location.replace(decision.targetUrl || '/blocked');
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
