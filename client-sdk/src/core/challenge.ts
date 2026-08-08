/** 挑战交互组件。
 *
 * FY-DISP-003 修复：为 mechanism=challenge 实现真实的挑战界面与校验流程。
 *
 * 设计要点：
 * - captcha：渲染「我不是机器人」按钮，点击后调用 /v2/challenge/verify 提交答案
 * - js：实现简化的 Proof-of-Work 挑战（客户端计算满足难度要求的哈希）
 * - 挑战完成后重新发起 decide 或刷新页面（由 onSuccess 回调决定）
 * - 支持 WordPress #fangyu-challenge 挂载点（FY-DISP-004）
 */

import type { DecisionResponse } from '../types';
import { ENDPOINTS } from '../config';
import { post } from '../utils/http';
import { sha256 } from '../utils/crypto';
import { generateNonce, signParams } from './signer';

export interface ChallengeContext {
  /** Gateway API 基址。 */
  apiBase: string;
  /** API Key，走 X-App-Key header。 */
  apiKey: string;
  /** App Secret，用于签名计算。 */
  appSecret?: string;
  /** 站点 ID（`Site.id`）。 */
  siteId: number;
  /** 访客指纹。 */
  fingerprint: string;
  /** 挑战类型。 */
  challengeKind?: 'captcha' | 'js';
  /** 挑战令牌。 */
  challengeToken?: string;
  /** 调试日志。 */
  debug?: boolean;
  /** PoW 挑战难度（前导零位数）。 */
  powDifficulty?: number;
  /** 时钟偏移（毫秒）。 */
  clockSkewMs?: number;
}

export interface ChallengeOptions {
  /** 挑战通过后的回调。不提供则默认刷新页面。 */
  onSuccess?: () => void;
  /** 挑战失败后的回调。不提供则默认显示错误提示。 */
  onError?: (message: string) => void;
}

interface VerifyPayload {
  siteId: number;
  fingerprint: string;
  challengeToken: string;
  answer: string;
}

interface VerifyResponse {
  success: boolean;
  message?: string | null;
  passTtl?: number | null;
}

interface SuccessEnvelope<T> {
  code: number;
  message: string;
  data: T;
}

/** 默认挑战难度：要求哈希前导零的位数（十六进制）。 */
const DEFAULT_POW_DIFFICULTY = 4;

/**
 * 渲染挑战界面并处理交互。
 *
 * @param decision    网关下发的决策响应，包含 challengeKind 和 challengeToken
 * @param context     API 配置与访客身份
 * @param options     成功/失败回调
 * @param container   挂载容器（可选）。未提供则创建全屏遮罩；提供则在容器内渲染
 */
export function mountChallenge(
  decision: DecisionResponse,
  context: ChallengeContext,
  options: ChallengeOptions = {},
  container?: HTMLElement,
): void {
  if (!decision.challengeToken) {
    logError(context, 'challengeToken 缺失，无法发起挑战');
    options.onError?.('挑战配置错误');
    return;
  }

  const kind = decision.challengeKind || 'captcha';
  const token = decision.challengeToken;

  // 挂载点：外部提供的容器（WordPress #fangyu-challenge）或新建全屏遮罩
  const mountPoint = container || createOverlay();

  if (kind === 'captcha') {
    renderCaptcha(mountPoint, token, context, options);
  } else {
    renderJsChallenge(mountPoint, token, context, options);
  }

  logDebug(context, `挑战界面已挂载`, { kind, hasContainer: !!container });
}

/**
 * 渲染 captcha 挑战：「我不是机器人」按钮。
 *
 * 当前为占位实现：点击即提交（answer 为时间戳），真实验证逻辑在服务端 TODO。
 * 后续接入 hCaptcha / reCAPTCHA / Turnstile 时，需替换为第三方组件。
 */
function renderCaptcha(
  container: HTMLElement,
  token: string,
  context: ChallengeContext,
  options: ChallengeOptions,
): void {
  container.innerHTML = `
    <div style="text-align:center">
      <h1 style="font-size:20px;margin:0 0 12px">人机验证</h1>
      <p style="margin:0 0 24px;color:#666">检测到异常访问特征，请完成验证后继续。</p>
      <button
        id="fangyu-captcha-btn"
        style="
          padding:12px 32px;
          font-size:16px;
          border:2px solid #333;
          border-radius:8px;
          background:#fff;
          cursor:pointer;
          transition:all 0.2s;
        "
        onmouseover="this.style.background='#f0f0f0'"
        onmouseout="this.style.background='#fff'"
      >
        ✓ 我不是机器人
      </button>
      <div id="fangyu-captcha-status" style="margin-top:16px;color:#999;font-size:14px"></div>
    </div>
  `;

  const btn = container.querySelector('#fangyu-captcha-btn') as HTMLButtonElement | null;
  const status = container.querySelector('#fangyu-captcha-status') as HTMLElement | null;

  if (!btn || !status) return;

  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.style.opacity = '0.5';
    btn.style.cursor = 'not-allowed';
    status.textContent = '正在验证...';
    status.style.color = '#999';

    // 占位答案：客户端时间戳。真实场景下应由第三方服务返回 token。
    const answer = String(Date.now());

    const result = await submitChallenge(token, answer, context);

    if (result.success) {
      status.textContent = '验证通过，即将跳转...';
      status.style.color = '#52c41a';
      setTimeout(() => {
        if (options.onSuccess) {
          options.onSuccess();
        } else {
          location.reload();
        }
      }, 800);
    } else {
      status.textContent = result.message || '验证失败，请重试';
      status.style.color = '#f5222d';
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.style.cursor = 'pointer';
      options.onError?.(result.message || '验证失败');
    }
  });
}

/**
 * 渲染 js 挑战：Proof-of-Work 计算界面。
 *
 * 客户端计算满足难度要求的哈希（前导零位数 >= POW_DIFFICULTY），
 * answer 为计算出的 nonce，服务端重算验证。
 */
function renderJsChallenge(
  container: HTMLElement,
  token: string,
  context: ChallengeContext,
  options: ChallengeOptions,
): void {
  container.innerHTML = `
    <div style="text-align:center">
      <h1 style="font-size:20px;margin:0 0 12px">浏览器验证</h1>
      <p style="margin:0 0 24px;color:#666">正在验证您的浏览器环境...</p>
      <div style="width:200px;height:4px;background:#e8e8e8;border-radius:2px;margin:0 auto;overflow:hidden">
        <div id="fangyu-pow-progress" style="height:100%;background:#1890ff;width:0;transition:width 0.3s"></div>
      </div>
      <div id="fangyu-pow-status" style="margin-top:16px;color:#999;font-size:14px">正在计算...</div>
    </div>
  `;

  const progress = container.querySelector('#fangyu-pow-progress') as HTMLElement | null;
  const status = container.querySelector('#fangyu-pow-status') as HTMLElement | null;

  if (!progress || !status) return;

  // 异步计算，避免阻塞 UI 渲染
  setTimeout(() => {
    const difficulty = context.powDifficulty ?? DEFAULT_POW_DIFFICULTY;
    void computeProofOfWork(token, difficulty, (percent) => {
      progress.style.width = `${percent}%`;
    }).then(async (nonce) => {
      if (nonce === null) {
        status.textContent = '计算失败，请刷新重试';
        status.style.color = '#f5222d';
        options.onError?.('PoW 计算失败');
        return;
      }

      status.textContent = '计算完成，正在提交...';
      const result = await submitChallenge(token, nonce, context);

      if (result.success) {
        status.textContent = '验证通过，即将跳转...';
        status.style.color = '#52c41a';
        setTimeout(() => {
          if (options.onSuccess) {
            options.onSuccess();
          } else {
            location.reload();
          }
        }, 800);
      } else {
        status.textContent = result.message || '验证失败';
        status.style.color = '#f5222d';
        options.onError?.(result.message || '验证失败');
      }
    });
  }, 100);
}

/**
 * Proof-of-Work 计算：寻找满足难度要求的 nonce。
 *
 * 目标：sha256(token + nonce) 的十六进制表示前 difficulty 位为 '0'。
 * 例如 difficulty=4 要求哈希以 "0000" 开头。
 *
 * @param token       challengeToken，服务端签发
 * @param difficulty  难度（前导零位数）
 * @param onProgress  进度回调，percent ∈ [0, 100]
 * @returns           满足条件的 nonce（十六进制字符串），失败返回 null
 */
async function computeProofOfWork(
  token: string,
  difficulty: number,
  onProgress: (percent: number) => void,
): Promise<string | null> {
  const prefix = '0'.repeat(difficulty);
  const maxAttempts = 1000000; // 上限 100 万次，避免无限循环
  const progressStep = Math.floor(maxAttempts / 100);

  for (let nonce = 0; nonce < maxAttempts; nonce++) {
    const input = token + nonce.toString(16);
    const hash = await sha256(input);

    if (hash.startsWith(prefix)) {
      onProgress(100);
      return nonce.toString(16);
    }

    if (nonce % progressStep === 0) {
      onProgress(Math.floor((nonce / maxAttempts) * 100));
      // 每 1% 让出主线程，避免阻塞 UI
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
  }

  return null; // 超过尝试上限
}

/**
 * 为挑战载荷附加签名字段。
 *
 * 与 `SdSdk.signBody` 同一套算法：补 timestamp/nonce 后整体 HMAC。
 * 这里独立实现是因为挑战组件可以脱离 SdSdk 实例运行（WordPress 挂载点场景）。
 *
 * @param payload     待签名的业务载荷
 * @param appSecret   站点签名密钥
 * @param clockSkewMs 与服务端的时钟偏移，纠正本地时间不准导致的时间戳越界
 */
async function signChallengePayload(
  payload: VerifyPayload,
  appSecret: string,
  clockSkewMs: number,
): Promise<Record<string, unknown>> {
  const signable: Record<string, unknown> = {
    ...payload,
    timestamp: Math.floor((Date.now() + clockSkewMs) / 1000),
    nonce: generateNonce(),
  };
  signable.sign = await signParams(signable, appSecret);
  return signable;
}

/**
 * 提交挑战答案到 /v2/challenge/verify。
 *
 * @param token   challengeToken
 * @param answer  captcha 的第三方 token 或 js 的 nonce
 * @param context API 配置与访客身份
 * @returns       校验结果
 */
async function submitChallenge(
  token: string,
  answer: string,
  context: ChallengeContext,
): Promise<VerifyResponse> {
  const url = `${context.apiBase}${ENDPOINTS.challengeVerify}`;
  const payload: VerifyPayload = {
    siteId: context.siteId,
    fingerprint: context.fingerprint,
    challengeToken: token,
    answer,
  };

  // 站点开启 signature_required 时必须签名，否则中间件直接 401。
  // 未配置 appSecret 视为未开启验签，原样提交。
  const requestBody = context.appSecret
    ? await signChallengePayload(payload, context.appSecret, context.clockSkewMs ?? 0)
    : payload;

  logDebug(context, `提交挑战答案`, { url, answerLength: answer.length, signed: !!context.appSecret });

  const response = await post<SuccessEnvelope<VerifyResponse>>(url, requestBody, {
    timeout: 10000,
    apiKey: context.apiKey,
  });

  if (!response.ok || !response.data) {
    logError(context, '挑战提交失败', response.error);
    return { success: false, message: '网络错误' };
  }

  const body = response.data;
  if (body.data) {
    return body.data;
  }

  // 兼容裸返（不带 SuccessEnvelope 包装）
  if (typeof (body as unknown as VerifyResponse).success === 'boolean') {
    return body as unknown as VerifyResponse;
  }

  return { success: false, message: '响应格式错误' };
}

/** 创建全屏遮罩容器。 */
function createOverlay(): HTMLElement {
  const overlay = document.createElement('div');
  overlay.setAttribute('data-fangyu-challenge-overlay', '1');
  overlay.style.cssText = [
    'position:fixed',
    'inset:0',
    'z-index:2147483647',
    'background:#fff',
    'display:flex',
    'align-items:center',
    'justify-content:center',
    'font-family:system-ui,-apple-system,sans-serif',
    'padding:24px',
  ].join(';');
  document.body.appendChild(overlay);
  return overlay;
}

function logDebug(context: ChallengeContext, message: string, data?: unknown): void {
  // rule-exception: [LOG-004] 原因: challenge.ts 可在非 SDK 场景独立使用（WordPress
  // 直接挂载挑战页），无法依赖外部日志工具。此处由 debug 开关保护，默认关闭。
  if (context.debug) {
    console.log(`[fangyu-challenge] ${message}`, data ?? '');
  }
}

function logError(context: ChallengeContext, message: string, error?: unknown): void {
  console.error(`[fangyu-challenge] ${message}`, error ?? '');
}
