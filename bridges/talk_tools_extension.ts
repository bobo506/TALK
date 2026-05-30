/**
 * TALK talk_send 工具扩展 — pi bridge 专用（5.5 step 1 最小可验证版）
 *
 * 注册 talk_send 工具，pi 通过 function-calling 发送消息给群内其他成员。
 * 工具 handler 直接向 TALK server 发 HTTP POST。
 *
 * 环境变量：
 *   TALK_BASE_URL — TALK server 地址（默认 http://127.0.0.1:8000）
 *   TALK_API_KEY   — 当前 agent 的 API Key（必需）
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import * as fs from "node:fs";
import * as path from "node:path";

// ---------------------------------------------------------------------------
// 从环境变量读取 TALK 连接配置
// ---------------------------------------------------------------------------
function getConfig() {
  return {
    baseUrl: process.env.TALK_BASE_URL || "http://127.0.0.1:8000",
    apiKey: process.env.TALK_API_KEY || "",
  };
}

// ---------------------------------------------------------------------------
// 向 TALK server 发送消息
// ---------------------------------------------------------------------------
async function sendToTalk(
  baseUrl: string,
  apiKey: string,
  target: string,
  body: string,
  groupId?: string,
): Promise<{ ok: boolean; messageId?: number; error?: string }> {
  const payload: Record<string, unknown> = {
    to: [target],
    type: "text",
    content: `@${target} ${body}`,
  };
  if (groupId) {
    payload.group_id = groupId;
  }

  try {
    const resp = await fetch(`${baseUrl}/api/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      return { ok: false, error: `HTTP ${resp.status}: ${text.slice(0, 200)}` };
    }

    const data = (await resp.json()) as { id: number };
    return { ok: true, messageId: data.id };
  } catch (err) {
    return { ok: false, error: String(err).slice(0, 200) };
  }
}

// ---------------------------------------------------------------------------
// 扩展入口
// ---------------------------------------------------------------------------
export default function talkToolsExtension(pi: ExtensionAPI) {
  const config = getConfig();

  if (!config.apiKey) {
    console.error("[TALK extension] TALK_API_KEY not set — talk_send will return errors");
  }

  pi.registerTool({
    name: "talk_send",
    label: "Send to TALK member",
    description:
      "向当前群内的指定成员发送消息。当你需要联系、转告、询问或通知另一成员时使用。" +
      "发送后你会收到确认。target 必须是群成员清单中列出的成员。",
    promptSnippet: "Send a message to another group member via TALK",
    promptGuidelines: [
      "当用户让你联系、转告、询问或通知群里另一成员时，调用 talk_send。",
      "调用后会收到工具执行结果，在可见回复里简要说明结果即可。",
      "target 必须是群成员清单中的完整 member_id，body 是消息正文（不要加 @ 前缀）。",
    ],
    parameters: Type.Object({
      target: Type.String({
        description: "目标成员完整 member_id（如 agent:codex），必须是群成员清单中的成员",
      }),
      body: Type.String({
        description: "消息正文，不要加 @ 前缀",
      }),
    }),

    async execute(_toolCallId, params) {
      if (!config.apiKey) {
        return {
          content: [{ type: "text", text: "talk_send 不可用：TALK_API_KEY 未设置" }],
          details: { error: "TALK_API_KEY not set" },
        };
      }

      const target = String(params.target || "").trim();
      const body = String(params.body || "").trim();
      const groupId = process.env.TALK_GROUP_ID || undefined;
      // 诊断
      try {
        const dumpPath = process.env.TALK_DUMP_PROMPT_FILE || "logs/pi_prompt_dump.log";
        const dumpDir = path.dirname(dumpPath);
        if (dumpDir) fs.mkdirSync(dumpDir, { recursive: true });
        fs.appendFileSync(dumpPath, `[${new Date().toISOString()}] talk_send: target=${target} group_id=${groupId || "(NONE)"} body_len=${body.length}\n`);
      } catch (_) {}

      if (!target || !body) {
        return {
          content: [{ type: "text", text: "talk_send 失败：缺少 target 或 body 参数" }],
          details: { error: "missing required parameter" },
        };
      }

      const result = await sendToTalk(config.baseUrl, config.apiKey, target, body, groupId);

      // 向 TALK server 发送消息（直接 HTTP POST）
      const result = await sendToTalk(config.baseUrl, config.apiKey, target, body, groupId);

      if (result.ok) {
        return {
          content: [{ type: "text", text: `已发送给 ${target}（消息 ID ${result.messageId}）。` }],
          details: { messageId: result.messageId, target, groupId },
        };
      }

      return {
        content: [{ type: "text", text: `发送失败：${result.error}` }],
        details: { error: result.error, target },
      };
    },
  });
}
