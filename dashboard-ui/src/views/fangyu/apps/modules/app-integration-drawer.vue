<!-- 接入指引抽屉：5-tab 接入代码，每种方式含四段式说明 -->
<template>
  <ElDrawer
    v-model="drawerVisible"
    :title="`接入指引 · ${app?.name}`"
    direction="rtl"
    size="680px"
    destroy-on-close
  >
    <ElAlert type="info" :closable="false" class="mb-4" show-icon>
      以下代码已自动填入当前站点的 Site ID 与 App Secret。
    </ElAlert>

    <!-- 网关地址（用户可改） -->
    <div class="flex items-center gap-2 mb-4">
      <span class="text-sm text-g-600 whitespace-nowrap">网关地址</span>
      <ElInput v-model="gatewayUrl" placeholder="https://defense.example.com" />
    </div>

    <ElTabs v-model="activeTab">

      <!-- ── Nginx-Lua ──────────────────────────────── -->
      <ElTabPane label="Nginx-Lua" name="nginx">
        <!-- 适用场景 -->
        <div class="section-block">
          <div class="section-title">适用场景</div>
          <p class="section-desc">适合部署在自建 VPS / 物理机上的 Nginx 站点，流量在服务端完成鉴别，App Secret 不暴露给浏览器。广告落地页、电商推荐等高价值场景首选。</p>
          <div class="tag-row">
            <ElTag type="success" size="small">服务端模式</ElTag>
            <ElTag type="success" size="small">Secret 安全</ElTag>
            <ElTag size="small">高并发友好</ElTag>
          </div>
        </div>
        <!-- 前提条件 -->
        <div class="section-block">
          <div class="section-title">前提条件</div>
          <ul class="prereq-list">
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>Nginx 已编译或动态加载 <code>ngx_http_lua_module</code>（OpenResty 自带）</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>拥有 Nginx 配置文件的 <code>sudo</code> 修改权限</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>已将 <code>defense.lua</code> 放至 <code>/etc/nginx/lua/fangyu/</code></li>
          </ul>
          <ElAlert type="info" :closable="false" size="small" class="mt-2" show-icon>
            defense.lua 可从网关管理页面或
            <a :href="`${gw}/sdk/defense.lua`" target="_blank" class="text-primary">{{ gw }}/sdk/defense.lua</a>
            下载。
          </ElAlert>
        </div>
        <!-- 代码 -->
        <div class="code-section">
          <div class="code-header">nginx.conf — server 块内添加</div>
          <pre class="code-block">{{ nginxCode }}</pre>
          <ElButton size="small" class="copy-btn" @click="copy(nginxCode)">复制</ElButton>
        </div>
        <!-- 注意事项 -->
        <div class="section-block">
          <div class="section-title">注意事项</div>
          <ul class="note-list">
            <li>修改配置后执行 <code>nginx -t && nginx -s reload</code> 使其生效。</li>
            <li><code>fangyu_fail_mode open</code> 表示网关不可达时放行，改为 <code>closed</code> 则拦截，建议生产先用 open 观察。</li>
            <li>App Secret 写入 nginx.conf 后注意控制文件权限（<code>chmod 640</code>），避免被其他进程读取。</li>
          </ul>
        </div>
      </ElTabPane>

      <!-- ── Cloudflare Worker ─────────────────────── -->
      <ElTabPane label="CF Worker" name="cf">
        <!-- 适用场景 -->
        <div class="section-block">
          <div class="section-title">适用场景</div>
          <p class="section-desc">域名已托管在 Cloudflare、且希望无需自建服务器的场景。Worker 在 Cloudflare 边缘节点运行，延迟极低，适合全球流量分发的落地页。</p>
          <div class="tag-row">
            <ElTag type="success" size="small">服务端模式</ElTag>
            <ElTag type="success" size="small">无需自建服务器</ElTag>
            <ElTag size="small">全球边缘加速</ElTag>
          </div>
        </div>
        <!-- 前提条件 -->
        <div class="section-block">
          <div class="section-title">前提条件</div>
          <ul class="prereq-list">
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>Cloudflare 账号，域名已接入 CF（橙云状态）</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>本地已安装 <code>wrangler</code> CLI（<code>npm install -g wrangler</code>）</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>已执行 <code>wrangler login</code> 完成授权</li>
          </ul>
        </div>
        <!-- 代码 -->
        <div class="code-section">
          <div class="code-header">wrangler.toml</div>
          <pre class="code-block">{{ cfTomlCode }}</pre>
          <ElButton size="small" class="copy-btn" @click="copy(cfTomlCode)">复制</ElButton>
        </div>
        <div class="code-section mt-3">
          <div class="code-header">密钥单独设置（终端执行，不进代码库）</div>
          <pre class="code-block">{{ cfSecretCmd }}</pre>
          <ElButton size="small" class="copy-btn" @click="copy(cfSecretCmd)">复制</ElButton>
        </div>
        <!-- 注意事项 -->
        <div class="section-block">
          <div class="section-title">注意事项</div>
          <ul class="note-list">
            <li><strong>绝对不要</strong>将 <code>FANGYU_APP_SECRET</code> 的值直接写入 <code>wrangler.toml</code> 并提交到代码库，应始终用 <code>wrangler secret put</code> 管理。</li>
            <li>Worker 免费计划每日有 10 万次请求限额，高流量站点请确认 CF 套餐。</li>
            <li>部署命令：<code>wrangler deploy</code>；本地调试：<code>wrangler dev</code>。</li>
          </ul>
        </div>
      </ElTabPane>

      <!-- ── WordPress ─────────────────────────────── -->
      <ElTabPane label="WordPress" name="wp">
        <!-- 适用场景 -->
        <div class="section-block">
          <div class="section-title">适用场景</div>
          <p class="section-desc">使用 WordPress 搭建的站点，通过插件或直接编辑配置文件即可接入，无需修改 Nginx。适合内容博客、WooCommerce 店铺等。</p>
          <div class="tag-row">
            <ElTag type="success" size="small">服务端模式</ElTag>
            <ElTag size="small">零代码运维</ElTag>
            <ElTag type="warning" size="small">需要 PHP ≥ 7.4</ElTag>
          </div>
        </div>
        <!-- 前提条件 -->
        <div class="section-block">
          <div class="section-title">前提条件</div>
          <ul class="prereq-list">
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>WordPress 版本 ≥ 5.0，PHP ≥ 7.4</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>已安装 <strong>Fangyu Defense</strong> WordPress 插件（或可直接编辑 <code>wp-config.php</code>）</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>服务器能向外发起 HTTP 请求（<code>allow_url_fopen</code> 或 cURL）</li>
          </ul>
        </div>
        <!-- 代码 -->
        <div class="code-section">
          <div class="code-header">wp-config.php（或插件设置页填写对应值）</div>
          <pre class="code-block">{{ wpCode }}</pre>
          <ElButton size="small" class="copy-btn" @click="copy(wpCode)">复制</ElButton>
        </div>
        <!-- 注意事项 -->
        <div class="section-block">
          <div class="section-title">注意事项</div>
          <ul class="note-list">
            <li>将 <code>define()</code> 语句添加在 <code>wp-config.php</code> 中 <code>/* That's all, stop editing! */</code> 注释行之前。</li>
            <li>使用缓存插件（如 WP Rocket / W3 Total Cache）时，请将登录页、结账页加入缓存排除列表，避免缓存绕过检测。</li>
            <li>安装插件后如出现白屏，优先检查 PHP 版本与 cURL 扩展是否开启。</li>
          </ul>
        </div>
      </ElTabPane>

      <!-- ── 网站 SDK ───────────────────────────────── -->
      <ElTabPane label="网站 SDK" name="sdk">
        <!-- 安全警告置顶 -->
        <ElAlert type="error" :closable="false" show-icon class="mb-3">
          <template #title>App Secret 不可用于客户端模式</template>
          网站 SDK 运行在浏览器中，任何人均可在源码中看到配置。<strong>此处只允许填写 siteId，App Secret 绝对不可出现在前端代码中。</strong>
        </ElAlert>
        <!-- 适用场景 -->
        <div class="section-block">
          <div class="section-title">适用场景</div>
          <p class="section-desc">纯静态页面或无法修改服务端的内容型站点。SDK 在访客浏览器中采集指纹并上报，由网关完成风险判断。此处适合 standalone 场景；如果站点已经接了 Nginx-Lua、CF Worker 或 WordPress 服务端层，请使用对应适配器标签页。</p>
          <div class="tag-row">
            <ElTag size="small">客户端模式</ElTag>
            <ElTag type="warning" size="small">Secret 不可用</ElTag>
            <ElTag type="danger" size="small">不推荐广告落地页</ElTag>
          </div>
        </div>
        <!-- 前提条件 -->
        <div class="section-block">
          <div class="section-title">前提条件</div>
          <ul class="prereq-list">
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>能修改页面 HTML（添加 <code>&lt;script&gt;</code> 标签）</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>访客浏览器需允许 JavaScript 执行</li>
          </ul>
        </div>
        <!-- 代码 -->
        <div class="code-section">
          <div class="code-header">HTML 嵌入（放在 &lt;head&gt; 内尽量靠前，不要加 defer / async）</div>
          <pre class="code-block">{{ sdkCode }}</pre>
          <ElButton size="small" class="copy-btn" @click="copy(sdkCode)">复制</ElButton>
        </div>
        <!-- 注意事项 -->
        <div class="section-block">
          <div class="section-title">注意事项</div>
          <ul class="note-list">
            <li><strong>必须放在 <code>&lt;head&gt;</code> 内尽量靠前的位置，且不要加 <code>defer</code> / <code>async</code></strong>。放到 <code>&lt;body&gt;</code> 底部或加 defer 会让判定推迟到页面资源加载完之后，表现为「先加载完整站再跳转」。</li>
            <li>同会话内的重复访问命中本地决策缓存，跳转为<strong>纯同步、零网络</strong>，在 body 解析前即完成；首次访问仍需要一次网关 RTT，是否能压进 100ms 取决于网关和访客的网络距离。</li>
            <li>命中跳转条件时会调用 <code>window.stop()</code> 中止剩余资源加载；<strong>放行的访客不受任何干预</strong>，渲染流程与未接入时一致。</li>
            <li>需要「判定完成前不暴露正文」的高价值页面，加 <code>hideUntilDecided: true</code>；配套的 <code>hideTimeout</code>（默认 300ms）会兜底强制显示，避免网络异常时白屏。</li>
            <li>需要在跳转前完成服务端拦截（连 HTML 都不下发）的场景，仍应使用 <strong>Nginx-Lua 或 CF Worker</strong> 的服务端模式；这类场景不要用本页的同步 SDK 片段。</li>
            <li>需要保留浏览器侧行为采集、但不想在首屏阻塞时，可改用 <code>protect()</code> + <code>defer</code> 的异步接入方式。</li>
          </ul>
        </div>
      </ElTabPane>

      <!-- ── Shopify ──────────────────────────────────── -->
      <ElTabPane label="Shopify" name="shopify">
        <!-- 适用场景 -->
        <div class="section-block">
          <div class="section-title">适用场景</div>
          <p class="section-desc">Shopify 托管商店，只能通过编辑 theme.liquid 接入。采用「内联快筛 + SDK 兜底」双层策略：回访用户读缓存零网络跳转，首访交给 SDK 完整判定。</p>
          <div class="tag-row">
            <ElTag size="small">客户端模式</ElTag>
            <ElTag type="warning" size="small">Secret 不可用</ElTag>
            <ElTag size="small">两层防护</ElTag>
          </div>
        </div>
        <!-- 前提条件 -->
        <div class="section-block">
          <div class="section-title">前提条件</div>
          <ul class="prereq-list">
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>Shopify 店铺管理员权限（编辑主题代码）</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>当前主题已发布（编辑未发布的主题不生效）</li>
          </ul>
        </div>
        <!-- 步骤 1：清理旧代码 -->
        <div class="section-block">
          <div class="section-title">步骤 1：清理旧接入代码</div>
          <ul class="note-list">
            <li>打开 <strong>Online Store → Themes → Edit code</strong></li>
            <li>在左侧搜索框输入 <code>sd-sdk</code>，删除所有包含 <code>SdSdk.protect</code> 或 <code>SdSdk.guard</code> 的代码片段</li>
            <li>常见位置：<code>layout/theme.liquid</code>、<code>snippets/scripts.liquid</code></li>
            <li><strong>特别注意</strong>：<code>{{ "{{ content_for_header }}" }}</code> 只能在 theme.liquid 中出现一次，如有重复需删除</li>
          </ul>
        </div>
        <!-- 代码 -->
        <div class="code-section">
          <div class="code-header">layout/theme.liquid — 在 &lt;head&gt; 下面第一行插入</div>
          <pre class="code-block">{{ shopifyCode }}</pre>
          <ElButton size="small" class="copy-btn" @click="copy(shopifyCode)">复制</ElButton>
        </div>
        <!-- 步骤 2：部署 -->
        <div class="section-block">
          <div class="section-title">步骤 2：保存并验证</div>
          <ul class="note-list">
            <li>点击右上角 <strong>Save</strong></li>
            <li>清空浏览器缓存或用隐私模式访问产品页</li>
            <li>右键 → <strong>查看网页源代码</strong>，搜索 <code>_fh</code>，能搜到说明已生效</li>
          </ul>
        </div>
        <!-- 注意事项 -->
        <div class="section-block">
          <div class="section-title">注意事项</div>
          <ul class="note-list">
            <li><strong>工作原理</strong>：内联脚本只在检测到 <code>_sd_0000</code> cookie 时才发起同步请求（回访用户），首访用户跳过快筛、直接由 SDK 完整判定。这避免了低区分度指纹污染身份识别。</li>
            <li><strong>首访延迟</strong>：首访需下载 SDK（300-500ms）+ 采集指纹（100-200ms）+ 网关决策（200ms），总延迟约 600-900ms。回访命中缓存时 < 10ms。</li>
            <li><strong>测试规则注意</strong>：「所有人都跳转」的测试规则会影响真实顾客，测试完记得删除或改成条件触发。</li>
            <li><strong>更彻底的方案</strong>：需要服务端层拦截（连 HTML 都不下发）的场景，应使用 Cloudflare Worker 部署 <code>adapters/shopify/cloudflare_worker/worker.js</code>，本 tab 的客户端方案无法阻止请求到达 Shopify。</li>
          </ul>
        </div>
      </ElTabPane>

      <!-- ── 直接 API ───────────────────────────────── -->
      <ElTabPane label="直接 API" name="api">
        <!-- 适用场景 -->
        <div class="section-block">
          <div class="section-title">适用场景</div>
          <p class="section-desc">自研后端（任意语言）需要主动调用风险决策接口，例如在订单提交前、注册时、广告回传前进行服务端校验。</p>
          <div class="tag-row">
            <ElTag type="success" size="small">服务端模式</ElTag>
            <ElTag size="small">任意语言</ElTag>
            <ElTag size="small">需实现签名</ElTag>
          </div>
        </div>
        <!-- 前提条件 -->
        <div class="section-block">
          <div class="section-title">前提条件</div>
          <ul class="prereq-list">
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>后端能发起 HTTPS 请求</li>
            <li><ElIcon class="check"><CircleCheckFilled /></ElIcon>已实现 HMAC-SHA256 签名（以 App Secret 为密钥）</li>
          </ul>
          <ElAlert type="info" :closable="false" size="small" class="mt-2" show-icon>
            签名算法文档：<a :href="`${gw}/docs/signing`" target="_blank" class="text-primary">{{ gw }}/docs/signing</a>
          </ElAlert>
        </div>
        <!-- 代码 -->
        <div class="code-section">
          <div class="code-header">cURL 请求示例</div>
          <pre class="code-block">{{ curlCode }}</pre>
          <ElButton size="small" class="copy-btn" @click="copy(curlCode)">复制</ElButton>
        </div>
        <!-- 跳转变量对照表 -->
        <div class="mt-4 rounded bg-g-50 p-3 text-sm text-g-600">
          <p class="font-medium text-g-900 mb-2">跳转 URL 支持的占位符变量</p>
          <p class="mb-2 text-xs text-g-500">在规则处置的跳转地址中使用以下变量，网关在每次请求时动态渲染：</p>
          <table class="w-full text-xs">
            <tbody>
              <tr v-for="v in REDIRECT_VARS" :key="v.ph">
                <td class="font-mono text-primary pr-3 pb-1 whitespace-nowrap">{{ v.ph }}</td>
                <td class="pb-1 text-g-700">{{ v.desc }}</td>
              </tr>
            </tbody>
          </table>
          <p class="mt-2 text-g-500 italic text-xs">示例：https://verify.example.com/?back={url_enc}&country={country}&fp={fingerprint_enc}</p>
        </div>
        <!-- 注意事项 -->
        <div class="section-block">
          <div class="section-title">注意事项</div>
          <ul class="note-list">
            <li><code>nonce</code> 为每次请求唯一随机字符串（建议 UUID），与 <code>timestamp</code> 共同防止重放攻击，服务端会拒绝 5 分钟以外的请求。</li>
            <li>请求超时建议设置为 <strong>800ms</strong>，超时时按业务需要选择放行或拦截（fail-open / fail-closed）。</li>
            <li>App Secret 仅存于服务端环境变量，不得硬编码进源码或提交到代码库。</li>
          </ul>
        </div>
      </ElTabPane>

    </ElTabs>
  </ElDrawer>
</template>

<script setup lang="ts">
  import { ElMessage } from 'element-plus'
  import { CircleCheckFilled } from '@element-plus/icons-vue'

  interface Props {
    visible: boolean
    app?: Partial<Api.Fangyu.Site> | null
  }
  interface Emits {
    (e: 'update:visible', value: boolean): void
  }

  const props = defineProps<Props>()
  const emit = defineEmits<Emits>()

  const drawerVisible = computed({
    get: () => props.visible,
    set: (v) => emit('update:visible', v),
  })

  const activeTab = ref('nginx')
  const gatewayUrl = ref(
    props.app?.gateway_url
    ?? import.meta.env.VITE_GATEWAY_URL
    ?? 'https://defense.example.com',
  )

  const siteId = computed(() => props.app?.site_id ?? 'YOUR_SITE_ID')
  const appSecret = computed(() => props.app?.app_secret ?? 'YOUR_APP_SECRET')
  const gw = computed(() => gatewayUrl.value.replace(/\/$/, ''))
  // SDK 的 appId 要的是数字主键（Site.id），不是 site_id 那个 site_<hex8> 字符串。
  // 两者用途不同：site_id 走 X-App-Key header 做身份识别，id 是租户维度。
  const numericAppId = computed(() => props.app?.id ?? 0)

  const REDIRECT_VARS = [
    { ph: '{url}',             desc: '访客原始 URL（明文）' },
    { ph: '{url_enc}',         desc: '访客原始 URL（URL 编码），适合做 redirect-back 参数' },
    { ph: '{path}',            desc: 'URL 路径（不含 query）' },
    { ph: '{query}',           desc: 'query 字符串（含前缀 ?）' },
    { ph: '{scheme}',          desc: '协议 http / https' },
    { ph: '{host}',            desc: '域名+端口' },
    { ph: '{ip}',              desc: '访客 IP' },
    { ph: '{ip_enc}',          desc: '访客 IP（URL 编码）' },
    { ph: '{fingerprint}',     desc: 'Evercookie 指纹（明文）' },
    { ph: '{fingerprint_enc}', desc: 'Evercookie 指纹（URL 编码）' },
    { ph: '{country}',         desc: 'GeoIP 国家码，如 CN / US' },
    { ph: '{verdict}',         desc: '决策结论：hostile / suspicious / clean / unknown' },
    { ph: '{score}',           desc: '风险分（浮点，如 82.5）' },
    { ph: '{score_int}',       desc: '风险分（整数，如 82）' },
    { ph: '{connection_type}', desc: '网络类型：datacenter / mobile / residential' },
    { ph: '{is_vpn}',          desc: 'VPN：1 或 0' },
    { ph: '{is_proxy}',        desc: '代理：1 或 0' },
    { ph: '{ua_enc}',          desc: 'User-Agent（URL 编码）' },
    { ph: '{referer_enc}',     desc: 'Referer（URL 编码）' },
    { ph: '{ingress}',         desc: '接入来源：sdk / adapter' },
    { ph: '{site_id}',         desc: '站点 ID（同 X-App-Key 值）' },
    { ph: '{request_id}',      desc: '请求唯一 ID（每次不同，用于防重放）' },
    { ph: '{ts}',              desc: 'Unix 时间戳（秒）' },
  ]

  const nginxCode = computed(() => `# nginx.conf — server 块内添加：
set $fangyu_gateway_url  "${gw.value}";
set $fangyu_site_id      "${siteId.value}";  # 同时作为 X-App-Key
set $fangyu_app_secret   "${appSecret.value}";
set $fangyu_fail_mode    "open";             # open | closed

access_by_lua_file /etc/nginx/lua/fangyu/defense.lua;`)

  const cfTomlCode = computed(() => `# wrangler.toml
[vars]
FANGYU_GATEWAY_URL = "${gw.value}"
FANGYU_SITE_ID     = "${siteId.value}"
FANGYU_FAIL_MODE   = "open"

# 注意：FANGYU_APP_SECRET 不在此文件设置，通过 wrangler secret 管理`)

  const cfSecretCmd = computed(
    () => `# 在终端执行（密钥不进代码库）：\nwrangler secret put FANGYU_APP_SECRET`,
  )

  const wpCode = computed(() => `<?php
// wp-config.php（或插件设置页）
// 添加在 "/* That's all, stop editing! */" 之前
define('FANGYU_GATEWAY_URL', '${gw.value}');
define('FANGYU_SITE_ID',     '${siteId.value}');  // 同时用作 X-App-Key
define('FANGYU_APP_SECRET',  '${appSecret.value}');`)

  // SDK 不读任何全局配置变量，必须显式调用 SdSdk.guard()。
  // 字段名以 client-sdk/src/config.ts 的 SdkConfig 为准：
  // apiBase / apiKey / appId 三者是 validateConfig() 强制校验的必填项。
  //
  // 本片段是 standalone 接入（无服务端层，SDK 是唯一防线），因此用同步 +
  // guard()。带 CF Worker / nginx-lua / WordPress 服务端层的站点不用这个片段，
  // 那三个适配器只在服务端判 pass 时才注入，且应保持 defer + protect()。
  //
  // 两处刻意的写法，都关乎跳转能否抢在页面渲染之前：
  // 1. 必须放在 <head> 内、且尽量靠前——此时 body 还没解析，站点资源尚未开始
  //    下载。放到 body 底部等于先把整站加载完才判定。
  // 2. script 标签不能加 defer/async：defer 会推迟到 DOMContentLoaded 之前才
  //    执行，async 时序不确定；两者都会让内联的 guard() 报 SdSdk is not defined。
  const sdkCode = computed(() => `<!-- 客户端 SDK 模式：仅 siteId 可公开，App Secret 绝对不可出现在前端 -->
<!-- 放在 <head> 内尽量靠前的位置，且不要加 defer / async -->
<script src="${gw.value}/sdk/sd-sdk.min.js"><\/script>
<script>
  SdSdk.guard({
    apiBase: '${gw.value}',
    apiKey:  '${siteId.value}',
    appId:   ${numericAppId.value}
    // 高价值页面可加：hideUntilDecided: true —— 判定完成前隐藏内容，
    // 防止 Bot 在跳转生效前抓到正文（默认关闭，不影响正常访客渲染）
  });
<\/script>`)

  const shopifyCode = computed(() => `<head>
  <meta charset="utf-8">

  {%- comment -%}Fangyu 防护{%- endcomment -%}
  <style id="_fh">html{visibility:hidden!important;opacity:0!important}</style>
  <script>
!function(){function e(){var e=document.getElementById("_fh");e&&e.remove(),document.documentElement.style.cssText="visibility:visible;opacity:1"}var t=document.cookie.match(/_sd_0000=([^;]+)/);if(!t)return void e();var n="_fr",o=sessionStorage.getItem(n);if(o===location.href)return sessionStorage.removeItem(n),void e();var r=null;try{r=JSON.parse(sessionStorage.getItem("_fc")||"null")}catch(e){}if(r&&r.e>Date.now()){if("redirect"===r.m&&r.u)return sessionStorage.setItem(n,location.href),void location.replace(r.u);if("pass"===r.m)return void e()}var a=new XMLHttpRequest;a.open("POST","${gw.value}/v2/decide",!1),a.setRequestHeader("Content-Type","application/json"),a.setRequestHeader("X-App-Key","${siteId.value}");var i=decodeURIComponent(t[1]);try{if(a.send(JSON.stringify({context:{appId:${numericAppId.value},ingress:"sdk",fingerprint:i,userAgent:navigator.userAgent,visitUrl:location.href,path:location.pathname,method:"GET",repeatKey:"_sd_0000",repeatValue:i}})),200===a.status){var c=JSON.parse(a.responseText),s=c.data||c;if(s.mechanism&&s.ttlSeconds>0&&sessionStorage.setItem("_fc",JSON.stringify({m:s.mechanism,u:s.targetUrl,e:Date.now()+Math.min(1e3*s.ttlSeconds,3e5)})),"redirect"===s.mechanism&&s.targetUrl)return sessionStorage.setItem(n,location.href),void location.replace(s.targetUrl);if("deny"===s.mechanism)return void(document.documentElement.innerHTML='<body style="text-align:center;padding:100px;font:sans-serif"><h1>403</h1></body>')}e()}catch(t){e()}}();
  <\/script>
  <script src="${gw.value}/sdk/sd-sdk.min.js" defer><\/script>
  <script>
document.addEventListener('DOMContentLoaded',function(){if(typeof SdSdk!=='undefined'){SdSdk.protect({apiBase:'${gw.value}',apiKey:'${siteId.value}',appId:${numericAppId.value},collectBehavior:true})}});
  <\/script>

  {%- if settings.favicon != blank -%}
    <link rel="icon" type="image/png" href="{{ "{{ settings.favicon | image_url: width: 32, height: 32 }}" }}">
  {%- endif -%}
  
  <!-- 后续原有代码保持不变 -->`)

  const curlCode = computed(() => `curl -X POST ${gw.value}/v2/decide \\
  -H "Content-Type" application/json" \\
  -H "X-App-Key: ${siteId.value}" \\
  -d '{
    "context": {
      "ingress":   "adapter",
      "ip":        "1.2.3.4",
      "userAgent": "Mozilla/5.0 ...",
      "visitUrl":  "https://yoursite.com/landing"
    },
    "timestamp": 1700000000,
    "nonce":     "abc123",
    "sign":      "<HMAC-SHA256>"
  }'`)

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      ElMessage.success('已复制')
    } catch {
      ElMessage.warning('请手动选中复制')
    }
  }
</script>

<style scoped>
  .section-block {
    margin-bottom: 16px;
  }
  .section-title {
    font-size: 12px;
    font-weight: 600;
    color: var(--el-text-color-secondary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
  }
  .section-desc {
    font-size: 13px;
    color: var(--el-text-color-regular);
    line-height: 1.6;
    margin: 0 0 8px;
  }
  .tag-row {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .prereq-list,
  .note-list {
    list-style: none;
    padding: 0;
    margin: 0;
    font-size: 13px;
    color: var(--el-text-color-regular);
  }
  .prereq-list li,
  .note-list li {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    margin-bottom: 6px;
    line-height: 1.5;
  }
  .prereq-list .check {
    color: var(--el-color-success);
    margin-top: 2px;
    flex-shrink: 0;
  }
  .note-list li::before {
    content: '·';
    color: var(--el-text-color-placeholder);
    flex-shrink: 0;
  }
  .code-section {
    position: relative;
    margin-bottom: 8px;
  }
  .code-header {
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-bottom: 4px;
    font-weight: 500;
  }
  .code-block {
    background: #1e1e2e;
    color: #cdd6f4;
    border-radius: 6px;
    padding: 12px 14px;
    font-size: 12px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
    max-height: 260px;
    overflow-y: auto;
  }
  .copy-btn {
    position: absolute;
    top: 24px;
    right: 8px;
  }
  code {
    background: var(--el-fill-color-light);
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 12px;
    font-family: monospace;
  }
</style>
