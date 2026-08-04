/** 浏览器指纹采集器。 */

import { djb2Hash } from '../utils/crypto';

export interface FingerprintItem {
  hash: string;
  raw: unknown;
}

export interface FingerprintData {
  canvas: FingerprintItem;
  webgl: FingerprintItem;
  audio: FingerprintItem;
  screen: FingerprintItem;
  webrtc: FingerprintItem;
  navigator: FingerprintItem;
  timezone: FingerprintItem;
  touchSupport: FingerprintItem;
  adBlock: FingerprintItem;
}

function hashData(data: unknown): FingerprintItem {
  return { hash: djb2Hash(JSON.stringify(data)), raw: data };
}

function errorItem(err: unknown): FingerprintItem {
  const message = err instanceof Error ? err.message : String(err);
  return hashData({ error: message });
}

/** Canvas 指纹：绘制混合内容后取 dataURL。 */
function getCanvasFingerprint(): FingerprintItem {
  try {
    const canvas = document.createElement('canvas');
    canvas.width = 280;
    canvas.height = 60;

    const ctx = canvas.getContext('2d');
    if (!ctx) return hashData({ error: 'no 2d context' });

    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillStyle = '#f60';
    ctx.fillRect(125, 1, 62, 20);

    ctx.fillStyle = '#069';
    ctx.fillText('Fangyu!<canvas> 2.0', 2, 15);
    ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
    ctx.fillText('Fangyu!<canvas> 2.0', 4, 17);

    ctx.fillStyle = '#f3c';
    ctx.beginPath();
    ctx.arc(50, 30, 15, 0, Math.PI * 2, true);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = '#0cf';
    ctx.beginPath();
    ctx.arc(100, 30, 12, 0, Math.PI * 2, true);
    ctx.closePath();
    ctx.fill();

    return hashData(canvas.toDataURL());
  } catch (e) {
    return errorItem(e);
  }
}

/** WebGL 指纹：厂商 / 渲染器 / 扩展列表。 */
function getWebGLFingerprint(): FingerprintItem {
  try {
    const canvas = document.createElement('canvas');
    const gl = (canvas.getContext('webgl') ||
      canvas.getContext('experimental-webgl')) as WebGLRenderingContext | null;

    if (!gl) return hashData({ error: 'no webgl context' });

    const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
    const renderer = debugInfo
      ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL)
      : 'unknown';
    const vendor = debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : 'unknown';

    const supported = gl.getSupportedExtensions() ?? [];

    return hashData({
      renderer: String(renderer),
      vendor: String(vendor),
      extensions: [...supported].sort(),
    });
  } catch (e) {
    return errorItem(e);
  }
}

/** suspended 与超时共用的载荷。
 *
 * 必须与原超时载荷逐字节一致：suspended 情形原本就是走满超时窗口后产出
 * 这个值，提前退出只改变**耗时**、不改变**结果**。载荷一旦变化，
 * `deriveFingerprintId` 的输出就变了，等于给存量访客换了个身份，
 * Clock 的频控与信誉聚合会整体断档。
 */
const AUDIO_UNAVAILABLE = { error: 'audio timeout' };

/** Audio 指纹：静音跑一段振荡器，取频域数据。
 *
 * 关键时序约束
 * ------------
 * `onaudioprocess` 仅在 AudioContext 处于 `running` 时触发。Chrome 的 autoplay
 * 策略让**没有用户手势的页面**（广告落地页的常态）拿到的 context 恒为
 * `suspended`，回调永不触发，必然走满超时。原实现超时 3000ms，仅这一项就足以
 * 把整条决策链路推到「页面全部加载完才跳转」。
 *
 * 因此 suspended 时立即退出，不调 `resume()`——它同样需要用户手势，
 * await 只会把延迟加回来。
 */
async function getAudioFingerprint(timeoutMs: number): Promise<FingerprintItem> {
  try {
    const Ctor =
      (globalThis as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext })
        .AudioContext ??
      (globalThis as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return hashData({ error: 'no AudioContext' });

    const ctx = new Ctor();

    // suspended：回调不会触发，等下去只是白等一整个超时窗口。
    if (ctx.state === 'suspended') {
      try {
        void ctx.close();
      } catch {
        // ignore
      }
      return hashData(AUDIO_UNAVAILABLE);
    }

    const oscillator = ctx.createOscillator();
    const analyser = ctx.createAnalyser();
    const gain = ctx.createGain();
    const processor = ctx.createScriptProcessor(4096, 1, 1);

    gain.gain.value = 0; // 静音，避免可听输出
    oscillator.type = 'triangle';
    oscillator.connect(analyser);
    analyser.connect(processor);
    processor.connect(gain);
    gain.connect(ctx.destination);

    const frequencyData = new Uint8Array(analyser.frequencyBinCount);

    return await new Promise<FingerprintItem>((resolve) => {
      const teardown = () => {
        try {
          oscillator.disconnect();
          processor.disconnect();
          analyser.disconnect();
          gain.disconnect();
          void ctx.close();
        } catch {
          // ignore
        }
      };

      const timeout = setTimeout(() => {
        teardown();
        resolve(hashData(AUDIO_UNAVAILABLE));
      }, timeoutMs);

      processor.onaudioprocess = () => {
        analyser.getByteFrequencyData(frequencyData);
        clearTimeout(timeout);
        const result = Array.from(frequencyData.slice(0, 30));
        teardown();
        resolve(hashData(result));
      };

      oscillator.start(0);
    });
  } catch (e) {
    return errorItem(e);
  }
}

function getScreenInfo(): FingerprintItem {
  try {
    return hashData({
      width: screen.width,
      height: screen.height,
      availWidth: screen.availWidth,
      availHeight: screen.availHeight,
      colorDepth: screen.colorDepth,
      pixelDepth: screen.pixelDepth,
      pixelRatio: window.devicePixelRatio || 1,
    });
  } catch {
    return hashData({ error: 'screen info unavailable' });
  }
}

/**
 * 媒体设备信息。
 *
 * 未授权时 `label` / `deviceId` 为空串，此处只用 kind 的组成做指纹——
 * 不主动请求权限，避免弹窗骚扰用户。
 */
async function getWebRTCInfo(): Promise<FingerprintItem> {
  try {
    const devices = await navigator.mediaDevices?.enumerateDevices();
    return hashData({
      devices: devices ? devices.map((d) => ({ kind: d.kind, label: d.label })) : [],
      mediaDevicesSupported: Boolean(navigator.mediaDevices),
    });
  } catch {
    return hashData({ error: 'webrtc unavailable' });
  }
}

function getNavigatorInfo(): FingerprintItem {
  try {
    const nav = navigator as Navigator & {
      deviceMemory?: number;
      productSub?: string;
      webdriver?: boolean;
    };
    return hashData({
      platform: nav.platform,
      language: nav.language,
      languages: nav.languages ? [...nav.languages] : [],
      hardwareConcurrency: nav.hardwareConcurrency || 0,
      deviceMemory: nav.deviceMemory || 0,
      userAgent: nav.userAgent,
      vendor: nav.vendor,
      productSub: nav.productSub ?? '',
      doNotTrack: nav.doNotTrack ?? '',
      cookieEnabled: nav.cookieEnabled,
      webdriver: Boolean(nav.webdriver),
    });
  } catch {
    return hashData({ error: 'navigator info unavailable' });
  }
}

function getTimezoneInfo(): FingerprintItem {
  try {
    return hashData({
      offset: new Date().getTimezoneOffset(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
  } catch {
    return hashData({ error: 'timezone unavailable' });
  }
}

function getTouchSupport(): FingerprintItem {
  try {
    return hashData({
      maxTouchPoints: navigator.maxTouchPoints || 0,
      touchStartSupport: 'ontouchstart' in window,
      touchEventSupport: Boolean(window.TouchEvent),
    });
  } catch {
    return hashData({ error: 'touch info unavailable' });
  }
}

/**
 * AdBlock 检测。
 *
 * 默认关闭：需要向第三方域名发请求，既有隐私成本又会在控制台留下报错。
 * 只在调用方显式开启 `thirdPartyProbe` 时执行。
 */
async function getAdBlockDetection(enabled: boolean): Promise<FingerprintItem> {
  if (!enabled) return hashData({ thirdPartyProbe: false });

  const testURLs = [
    'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js',
    'https://www.google-analytics.com/analytics.js',
    'https://connect.facebook.net/en_US/fbevents.js',
  ];

  const indicators: Record<string, boolean> = {};
  await Promise.all(
    testURLs.map(async (url) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 2000);
      try {
        await fetch(url, { method: 'HEAD', mode: 'no-cors', signal: controller.signal });
        indicators[url] = false;
      } catch {
        indicators[url] = true; // 被拦截或网络不可达
      } finally {
        clearTimeout(timer);
      }
    }),
  );

  return hashData(indicators);
}

/** 采集完整指纹。
 *
 * `audioTimeout` 默认 800ms：`running` 的 context 首个 `onaudioprocess` 在
 * 4096 帧缓冲 / 44.1kHz 下约 93ms 触发，800ms 已是充裕上限。原值 3000ms 是
 * 纯粹的空等余量，直接压在决策链路的关键路径上。
 */
export async function collectAll(
  options: { thirdPartyProbe?: boolean; audioTimeout?: number } = {},
): Promise<FingerprintData> {
  const [audio, webrtc, adBlock] = await Promise.all([
    getAudioFingerprint(options.audioTimeout ?? 800),
    getWebRTCInfo(),
    getAdBlockDetection(options.thirdPartyProbe === true),
  ]);

  return {
    canvas: getCanvasFingerprint(),
    webgl: getWebGLFingerprint(),
    audio,
    screen: getScreenInfo(),
    webrtc,
    navigator: getNavigatorInfo(),
    timezone: getTimezoneInfo(),
    touchSupport: getTouchSupport(),
    adBlock,
  };
}

/**
 * 从指纹数据派生稳定的 finger id。
 *
 * 只取稳定分量：`webrtc` 与 `adBlock` 会随权限状态和网络状况变化，纳入会让
 * 同一设备在不同时刻算出不同 id，直接破坏 Clock 的频控与信誉聚合。
 */
export function deriveFingerprintId(data: FingerprintData): string {
  const source = [
    data.canvas.hash,
    data.webgl.hash,
    data.audio.hash,
    data.screen.hash,
    data.navigator.hash,
    data.timezone.hash,
    data.touchSupport.hash,
  ].join('|');
  return djb2Hash(source);
}
