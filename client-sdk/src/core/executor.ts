/** 处置执行器：把网关返回的 mechanism 落到浏览器行为上。
 *
 * V1 没有这一层——它把 `jump` / `jump_mode` 之类的字段丢给调用方自己解释，
 * 每个接入站点都要重写一遍跳转逻辑。V2 把三层处置模型的执行收拢在此。
 *
 * 安全边界
 * --------
 * `serve_alt` 会把网关下发的 `pageContent` 写进 DOM。内容源是站点自己在后台
 * 配置的页面资源，不是访客可控输入，因此这里**按可信 HTML 处理**。风险点在
 * 于后台配置权限——那属于 admin 侧的权限模型，不在 SDK 兜底范围内。
 * 跳转目标做了协议白名单，挡掉 `javascript:` 这类伪协议。
 */

import type { DecisionResponse } from '../types';
import { mountChallenge, type ChallengeContext } from './challenge';

export interface ExecutorHooks {
  /** 返回 true 表示已自行处理，执行器不再动 DOM。 */
  onDecision?: (decision: DecisionResponse) => boolean | void;
  onChallenge?: (decision: DecisionResponse) => void;
}

export interface ExecutorContext {
  /** Gateway API 基址，用于 challenge 提交答案。 */
  apiBase?: string;
  /** API Key，用于 challenge 校验请求。 */
  apiKey?: string;
  /** 应用 ID。 */
  appId?: number;
  /** 访客指纹。 */
  fingerprint?: string;
  /** 调试日志。 */
  debug?: boolean;
}

export interface ApplyOutcome {
  /** 是否对页面做了干预。 */
  applied: boolean;
  action: 'none' | 'serve_alt' | 'redirect' | 'challenge' | 'block' | 'skipped';
}

/** 只允许跳到这些协议，挡掉 javascript: / data: 伪协议。 */
const SAFE_PROTOCOLS = new Set(['http:', 'https:']);

function isSafeUrl(raw: string): boolean {
  try {
    // 相对路径由 base 补全后必然是 http(s)，因此同样安全
    const url = new URL(raw, location.href);
    return SAFE_PROTOCOLS.has(url.protocol);
  } catch {
    return false;
  }
}

/** 执行处置。 */
export function applyDecision(
  decision: DecisionResponse,
  hooks: ExecutorHooks = {},
  context?: ExecutorContext,
): ApplyOutcome {
  if (hooks.onDecision?.(decision) === true) {
    return { applied: false, action: 'skipped' };
  }

  switch (decision.mechanism) {
    case 'pass':
      return { applied: false, action: 'none' };

    case 'serve_alt': {
      if (!decision.pageContent) {
        // 网关判了 serve_alt 但没给内容：资源被禁用或删除。不能当放行处理（会把该拦的
        // 流量放过去），也不能白屏。退化成 URL 跳转（若有），否则按阻断展示。
        console.warn(
          '[fangyu] serve_alt without pageContent, resource may be disabled/deleted',
          { requestId: decision.requestId, targetUrl: decision.targetUrl }
        );
        if (decision.targetUrl && isSafeUrl(decision.targetUrl)) {
          location.replace(decision.targetUrl);
          return { applied: true, action: 'redirect' };
        }
        renderBlockScreen(decision);
        return { applied: true, action: 'block' };
      }
      replaceDocument(decision.pageContent);
      return { applied: true, action: 'serve_alt' };
    }

    case 'redirect': {
      if (!decision.targetUrl || !isSafeUrl(decision.targetUrl)) {
        renderBlockScreen(decision);
        return { applied: true, action: 'block' };
      }
      // replace 而不是 assign：不给返回键留回到被拦页面的机会
      location.replace(decision.targetUrl);
      return { applied: true, action: 'redirect' };
    }

    case 'challenge': {
      hooks.onChallenge?.(decision);
      renderChallengeScreen(decision, context);
      return { applied: true, action: 'challenge' };
    }

    case 'deny':
    case 'not_found': {
      renderBlockScreen(decision);
      return { applied: true, action: 'block' };
    }

    default:
      // 未知机制：SDK 侧无 failMode 概念（页面已加载，阻断意义有限），
      // 但必须留下痕迹，否则后端新增机制而 SDK 未升级时会无声退化为放行。
      console.warn('[fangyu] unknown mechanism:', decision.mechanism);
      return { applied: false, action: 'none' };
  }
}

/**
 * 用替代内容整体替换当前文档。
 *
 * 用 `document.write` 而不是 `innerHTML`：替代页通常是完整 HTML（含 head、
 * 样式、脚本），`innerHTML` 塞进 body 会让 head 内容失效且脚本不执行。
 */
function replaceDocument(html: string): void {
  try {
    document.open();
    document.write(html);
    document.close();
  } catch {
    // document.write 在已加载完成的文档上可能被拒；退化到整体替换 documentElement
    try {
      document.documentElement.innerHTML = html;
    } catch {
      // 放弃干预，保持原页面
    }
  }
}

function renderChallengeScreen(decision: DecisionResponse, context?: ExecutorContext): void {
  // 如果外部提供了 context（包含 apiBase 等），使用真实挑战组件（FY-DISP-003 修复）
  if (context?.apiBase && context?.apiKey && context?.appId && context?.fingerprint) {
    const challengeContext: ChallengeContext = {
      apiBase: context.apiBase,
      apiKey: context.apiKey,
      appId: context.appId,
      fingerprint: context.fingerprint,
      debug: context.debug,
    };
    mountChallenge(decision, challengeContext, {
      onSuccess: () => location.reload(),
      onError: (msg) => console.error('[fangyu] 挑战失败:', msg),
    });
  } else {
    // 降级：context 不完整时显示占位界面（兼容旧调用方式）
    const kind = decision.challengeKind === 'js' ? 'JS 校验' : '人机校验';
    renderOverlay(`
      <h1 style="font-size:20px;margin:0 0 12px">需要完成${kind}</h1>
      <p style="margin:0;color:#666">检测到异常访问特征，请完成校验后继续。</p>
      <p style="margin:12px 0 0;color:#f5222d;font-size:12px">挑战配置不完整，请检查 SDK 初始化参数。</p>
    `);
  }
}

function renderBlockScreen(decision: DecisionResponse): void {
  const title = decision.mechanism === 'not_found' ? '页面不存在' : '访问被拒绝';
  renderOverlay(`
    <h1 style="font-size:20px;margin:0 0 12px">${title}</h1>
    <p style="margin:0;color:#666">${decision.httpStatus}</p>
  `);
}

/** 渲染全屏遮罩。内容由本模块内联构造，不含外部输入。 */
function renderOverlay(inner: string): void {
  try {
    const overlay = document.createElement('div');
    overlay.setAttribute('data-sd-overlay', '1');
    overlay.style.cssText = [
      'position:fixed',
      'inset:0',
      'z-index:2147483647',
      'background:#fff',
      'display:flex',
      'align-items:center',
      'justify-content:center',
      'text-align:center',
      'font-family:system-ui,-apple-system,sans-serif',
      'padding:24px',
    ].join(';');
    overlay.innerHTML = `<div style="max-width:420px">${inner}</div>`;
    document.body.appendChild(overlay);
  } catch {
    // 静默失败
  }
}
