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

type JsonObject = Record<string, any>;

function effectiveProjectId(value?: unknown): string | undefined {
  return String(value || process.env.TALK_PROJECT_ID || "").trim() || undefined;
}

async function apiRequest(
  method: string,
  apiPath: string,
  body?: JsonObject,
  params?: JsonObject,
): Promise<any> {
  const config = getConfig();
  if (!config.apiKey) throw new Error("TALK_API_KEY 未设置");
  const url = new URL(apiPath, config.baseUrl + "/");
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  const response = await fetch(url, {
    method,
    headers: {
      "X-API-Key": config.apiKey,
      "Accept": "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json; charset=utf-8" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let payload: any = null;
  if (text) {
    try { payload = JSON.parse(text); } catch (_) { payload = text; }
  }
  if (!response.ok) {
    const detail = payload && typeof payload === "object" ? payload.detail || payload : payload;
    throw new Error(`TALK API HTTP ${response.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return payload;
}

function availability(statuses: string[]): string {
  if (statuses.includes("busy")) return "busy";
  if (statuses.some((status) => ["online", "idle", "starting"].includes(status))) return "available";
  if (statuses.includes("error")) return "error";
  return "offline";
}

async function taskWithMessages(taskId: number): Promise<JsonObject> {
  const task = await apiRequest("GET", `/api/tasks/${taskId}`);
  const params: JsonObject = { limit: 50 };
  if (task.hall_group_id) params.group_id = task.hall_group_id;
  const messages = await apiRequest("GET", "/api/messages", undefined, params);
  return {
    task,
    messages,
    result_message: messages.find((message: JsonObject) => message.id === task.result_message_id) || null,
  };
}

async function replyTask(
  taskId: number,
  body: string,
  workflowAction = "none",
  allowAdditionalRound = false,
): Promise<JsonObject> {
  const allowedActions = [
    "none", "request_clarification", "submit_clarification_answer", "resolve_clarification", "accept",
  ];
  if (!allowedActions.includes(workflowAction)) {
    throw new Error(
      "workflow_action 必须是 none、request_clarification、submit_clarification_answer、resolve_clarification 或 accept",
    );
  }
  let task = await apiRequest("GET", `/api/tasks/${taskId}`);
  const currentMemberId = process.env.TALK_MEMBER_ID || (await apiRequest("GET", "/api/members/me")).id;
  let target: string;
  if (currentMemberId === task.created_by) target = task.target_member_id;
  else if (currentMemberId === task.target_member_id) target = task.created_by;
  else throw new Error("当前成员不是该 Task Hall 的请求者或执行者");

  const messageBody: JsonObject = { type: "text", content: body, to: [target] };
  if (task.hall_group_id) messageBody.group_id = task.hall_group_id;
  const message = await apiRequest("POST", "/api/messages", messageBody);
  if (workflowAction === "request_clarification") {
    task = await apiRequest(
      "POST", `/api/tasks/${taskId}/request-clarification`, { question_message_id: message.id },
    );
  } else if (workflowAction === "submit_clarification_answer") {
    task = await apiRequest(
      "POST", `/api/tasks/${taskId}/submit-clarification-answer`, { answer_message_id: message.id },
    );
  } else if (workflowAction === "resolve_clarification") {
    task = await apiRequest(
      "POST", `/api/tasks/${taskId}/resolve-clarification`,
      { allow_additional_round: Boolean(allowAdditionalRound) },
    );
  } else if (workflowAction === "accept") {
    task = await apiRequest("POST", `/api/tasks/${taskId}/accept`);
  }
  return { task, message };
}

async function toolResponse(operation: () => Promise<any>) {
  try {
    const payload = await operation();
    return {
      content: [{ type: "text", text: JSON.stringify(payload) }],
      details: payload,
    };
  } catch (err) {
    return {
      content: [{ type: "text", text: `TALK 工具失败：${String(err)}` }],
      details: { error: String(err) },
    };
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

  pi.registerTool({
    name: "talk_list_agents",
    label: "List TALK agents",
    description: "列出当前项目可委派的 Agent 及其实例忙闲状态。",
    parameters: Type.Object({ project_id: Type.Optional(Type.String()) }),
    async execute(_toolCallId, params) {
      return toolResponse(async () => {
        const projectId = effectiveProjectId(params.project_id);
        const members = await apiRequest("GET", "/api/members");
        const instances = await apiRequest("GET", "/api/instances");
        let projectMembers: Set<string> | undefined;
        if (projectId) {
          const projectAgents = await apiRequest("GET", `/api/projects/${encodeURIComponent(projectId)}/agents`);
          projectMembers = new Set(projectAgents.map((agent: JsonObject) => String(agent.member_id)));
        }
        const agents = members
          .filter((member: JsonObject) => member.kind === "agent" && !member.disabled_at)
          .filter((member: JsonObject) => !projectMembers || projectMembers.has(String(member.id)))
          .map((member: JsonObject) => {
            const memberInstances = instances.filter((instance: JsonObject) => instance.member_id === member.id);
            return {
              member_id: member.id,
              display_name: member.display_name,
              availability: availability(memberInstances.map((instance: JsonObject) => String(instance.status || "offline"))),
              instances: memberInstances,
            };
          });
        return { project_id: projectId || null, agents };
      });
    },
  });

  pi.registerTool({
    name: "talk_delegate_task",
    label: "Delegate TALK task",
    description: "向指定 Agent 创建项目化任务并自动建立独立 Task Hall。",
    parameters: Type.Object({
      project_id: Type.Optional(Type.String()),
      target_member_id: Type.String(),
      title: Type.Optional(Type.String()),
      content: Type.String(),
    }),
    async execute(_toolCallId, params) {
      return toolResponse(async () => {
        const projectId = effectiveProjectId(params.project_id);
        if (!projectId) throw new Error("缺少 project_id，且当前 bridge 未设置 TALK_PROJECT_ID");
        return apiRequest("POST", "/api/tasks", {
          project_id: projectId,
          target_member_id: String(params.target_member_id || "").trim(),
          title: String(params.title || "").trim() || null,
          content: String(params.content || "").trim(),
        });
      });
    },
  });

  pi.registerTool({
    name: "talk_get_task",
    label: "Get TALK task",
    description: "读取一个任务、Task Hall 最近消息及关联结果。",
    parameters: Type.Object({ task_id: Type.Number() }),
    async execute(_toolCallId, params) {
      return toolResponse(() => taskWithMessages(Number(params.task_id)));
    },
  });

  pi.registerTool({
    name: "talk_list_tasks",
    label: "List TALK tasks",
    description: "按项目、目标 Agent、runner 状态或协作状态查询可见任务。",
    parameters: Type.Object({
      project_id: Type.Optional(Type.String()),
      target_member_id: Type.Optional(Type.String()),
      status: Type.Optional(Type.String()),
      workflow_status: Type.Optional(Type.String()),
    }),
    async execute(_toolCallId, params) {
      return toolResponse(async () => {
        const projectId = effectiveProjectId(params.project_id);
        const tasks = await apiRequest("GET", "/api/tasks", undefined, {
          project_id: projectId,
          target_member_id: params.target_member_id,
          status: params.status,
          workflow_status: params.workflow_status,
        });
        return { project_id: projectId || null, tasks };
      });
    },
  });

  pi.registerTool({
    name: "talk_wait_tasks",
    label: "Wait for TALK tasks",
    description: "等待任务进入澄清、已提交、完成或失败等指定协作状态，最长 30 秒。",
    parameters: Type.Object({
      project_id: Type.Optional(Type.String()),
      task_ids: Type.Optional(Type.Array(Type.Number())),
      workflow_statuses: Type.Optional(Type.Array(Type.String())),
      timeout_seconds: Type.Optional(Type.Number()),
    }),
    async execute(_toolCallId, params) {
      return toolResponse(async () => {
        const desired = new Set((params.workflow_statuses || [
          "clarification_requested", "clarification_answered", "needs_decision",
          "submitted", "completed", "failed", "canceled",
        ]).map((status: unknown) => String(status).trim().toLowerCase()).filter(Boolean));
        const timeout = Math.max(0, Math.min(Number(params.timeout_seconds ?? 10), 30));
        const deadline = Date.now() + timeout * 1000;
        let tasks: JsonObject[] = [];
        while (true) {
          if (params.task_ids && params.task_ids.length) {
            tasks = await Promise.all(params.task_ids.map((taskId: number) => apiRequest("GET", `/api/tasks/${taskId}`)));
          } else {
            tasks = await apiRequest("GET", "/api/tasks", undefined, {
              project_id: effectiveProjectId(params.project_id),
            });
          }
          const matched = tasks.filter((task) => desired.has(String(task.workflow_status || "")));
          if (matched.length) return { timed_out: false, workflow_statuses: [...desired].sort(), tasks: matched };
          if (Date.now() >= deadline) return { timed_out: true, workflow_statuses: [...desired].sort(), tasks };
          await new Promise((resolve) => setTimeout(resolve, Math.min(500, Math.max(0, deadline - Date.now()))));
        }
      });
    },
  });

  pi.registerTool({
    name: "talk_reply_task",
    label: "Reply in TALK task",
    description: "在 Task Hall 回复，并可同步请求澄清、明确提交回答、释放人工决策或接受任务。",
    parameters: Type.Object({
      task_id: Type.Number(),
      body: Type.String(),
      workflow_action: Type.Optional(Type.String()),
      allow_additional_round: Type.Optional(Type.Boolean()),
    }),
    async execute(_toolCallId, params) {
      return toolResponse(() => replyTask(
        Number(params.task_id),
        String(params.body || "").trim(),
        String(params.workflow_action || "none").trim().toLowerCase(),
        Boolean(params.allow_additional_round || false),
      ));
    },
  });

  pi.registerTool({
    name: "talk_cancel_task",
    label: "Cancel TALK task",
    description: "原请求者取消尚未 claim 的任务；运行中任务暂不支持强制取消。",
    parameters: Type.Object({
      task_id: Type.Number(),
      reason: Type.Optional(Type.String()),
    }),
    async execute(_toolCallId, params) {
      return toolResponse(async () => {
        const taskId = Number(params.task_id);
        const task = await apiRequest("GET", `/api/tasks/${taskId}`);
        if (!["queued", "canceled"].includes(task.status)) {
          throw new Error("当前仅支持取消尚未 claim 的任务；运行中取消等待 runner 协作中断协议");
        }
        let message = null;
        const reason = String(params.reason || "").trim();
        if (reason && task.status !== "canceled") message = (await replyTask(taskId, reason)).message;
        const canceled = await apiRequest("POST", `/api/tasks/${taskId}/cancel`);
        return { task: canceled, message };
      });
    },
  });

  pi.registerTool({
    name: "talk_collect_result",
    label: "Collect TALK result",
    description: "原请求者收取已提交结果，并返回结果消息与 Task Hall 最近消息。",
    parameters: Type.Object({ task_id: Type.Number() }),
    async execute(_toolCallId, params) {
      return toolResponse(async () => {
        const taskId = Number(params.task_id);
        const task = await apiRequest("GET", `/api/tasks/${taskId}`);
        if (task.workflow_status === "submitted") await apiRequest("POST", `/api/tasks/${taskId}/collect-result`);
        else if (task.workflow_status !== "completed") throw new Error(`任务协作状态为 ${task.workflow_status}，尚无可收取结果`);
        return taskWithMessages(taskId);
      });
    },
  });
}
