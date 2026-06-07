/**
 * TALK talk_send 工具扩展 — pi bridge 专用（5.5 step 2+ P0 修复）
 *
 * 注册 talk_send 工具，pi 通过 function-calling 发送消息给群内其他成员。
 *
 * 延迟模式（唯一模式）：写 JSONL 到 TALK_DEFERRED_FILE，bridge 在 visible reply 后执行发送。
 * TALK_DEFERRED_FILE 未设置时（如 agent-to-agent 消息）返回不可用。
 *
 * 环境变量：
 *   TALK_API_KEY        — 当前 agent 的 API Key（用于校验）
 *   TALK_DEFERRED_FILE  — 延迟动作 JSONL 文件路径（bridge 创建、extension 写入、bridge 消费）
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
      "发送后你会收到确认。target 必须是群成员清单中列出的成员。" +
      " stance 参数标记消息类型：question（提问时用）、greeting（寒暄/打招呼时用）、answer/agree/disagree/closure。",
    promptSnippet:
      "当 human 明确要求你联系、转告、询问、通知或打招呼给另一位群成员时，使用 talk_send 发送消息。",
    promptGuidelines: [
      "当 human 明确让你联系、转告、询问或通知群里另一成员时，调用 talk_send。调用后在可见回复里简要告诉 human 已发送即可。",
      "调用 talk_send 时,body 是你以自己的 member_id 身份写给目标的话。不要逐字转发原始指令,不要在 body 里冒充请求者(例如不要写'我是 qa…',你不是 qa)。",
      "如果其他 agent 给你发了消息（寒暄/闲聊/确认）：只需自然回应，不要加'已回复 X'之类的任务汇报。不要再调用 talk_send，除非对方明确向你提出了一个需要回答的问题（stance=question）。",
      "调用 talk_send 时务必填写 stance：提问用 question，打招呼用 greeting，回答用 answer。",
      "target 必须是群成员清单中的完整 member_id，body 是消息正文（不要加 @ 前缀）。",
    ],
    parameters: Type.Object({
      target: Type.String({
        description: "目标成员完整 member_id（如 agent:codex），必须是群成员清单中的成员",
      }),
      body: Type.String({
        description: "消息正文，不要加 @ 前缀",
      }),
      stance: Type.Optional(Type.String({
        description: "消息立场（可选）。question=提问, answer=回答, agree=同意, disagree=反对, greeting=寒暄, closure=收尾。不填默认 greeting",
      })),
    }),

    async execute(_toolCallId, params) {
      if (!config.apiKey) {
        return {
          content: [{ type: "text", text: "talk_send 不可用：TALK_API_KEY 未设置" }],
          details: { error: "TALK_API_KEY not set" },
        };
      }

      const target = String(params.target || params.agent || "").trim();
      const body = String(params.body || params.message || "").trim();
      const stance = String(params.stance || "greeting").trim() || "greeting";
      const groupId = process.env.TALK_GROUP_ID || undefined;
      // 诊断
      try {
        const dumpPath = process.env.TALK_DUMP_PROMPT_FILE || "logs/pi_prompt_dump.log";
        const dumpDir = path.dirname(dumpPath);
        if (dumpDir) fs.mkdirSync(dumpDir, { recursive: true });
        fs.appendFileSync(dumpPath, `[${new Date().toISOString()}] talk_send: target=${target} stance=${stance} group_id=${groupId || "(NONE)"} body_len=${body.length}\n`);
      } catch (_) {}

      if (!target || !body) {
        return {
          content: [{ type: "text", text: "talk_send 失败：缺少 target 或 body 参数" }],
          details: { error: "missing required parameter" },
        };
      }

      // ---- deferred mode：写 JSONL，由 bridge 在 agent 结束后执行发送 ----
      const deferredFile = process.env.TALK_DEFERRED_FILE;
      if (deferredFile) {
        try {
          const dir = path.dirname(deferredFile);
          if (dir) fs.mkdirSync(dir, { recursive: true });
          const record = JSON.stringify({ tool: "talk_send", target, body, stance, group_id: groupId || null });
          fs.appendFileSync(deferredFile, record + "\n");
          return {
            content: [{ type: "text", text: `talk_send 已登记：将向 ${target} 发送消息（本轮结束后执行）。` }],
            details: { deferred: true, target, groupId },
          };
        } catch (err) {
          return {
            content: [{ type: "text", text: `talk_send 登记失败：${String(err)}` }],
            details: { error: "deferred write failed" },
          };
        }
      }

      // TALK_DEFERRED_FILE 未设置 = bridge 未授权（如 agent-to-agent 消息），返回不可用
      return {
        content: [{ type: "text", text: "talk_send 暂不可用（当前消息不需要向其他成员发送）。" }],
        details: { error: "talk_send not available for this message" },
      };
    },
  });
}
