# PPT 生成完整数据流

## 概述

本文档描述了从用户发起 PPT 生成请求到最终下载 PPT 文件的完整数据流。

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户请求阶段                                    │
└─────────────────────────────────────────────────────────────────────────────┘

[前端 ChatInterface]
    │
    │ POST /api/chat/stream
    │ {"message": "帮我为论文 41969395 生成PPT"}
    ↓
[main_api]
    │
    │ A2A 流式调用
    ↓
[search_agent]
    │
    │ LLM 识别意图，调用 generate_ppt_tool
    ↓
[generate_ppt_tool]
    │
    │ 1. 构造 tool_request 消息
    │ 2. 发送到 RabbitMQ question_queue
    │ 3. 立即返回 "accepted" JSONCARD
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                              返回给前端                                      │
└─────────────────────────────────────────────────────────────────────────────┘

[search_agent] → [main_api] → [前端]
    │
    │ A2A artifact-update 事件
    │ 包含: ```JSONCARD
    │       [{"type": "task", "id": "task_xxx", "payload": {"status": "accepted"}}]
    │       ```
    ↓
[前端 ChatInterface]
    │
    │ 解析 JSONCARD，渲染 TaskCard
    ↓
[TaskCard 组件]
    │
    │ 建立 WebSocket 连接到 subagent_main
    │ ws://subagent_main/ws/{task_id}
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                           后台异步处理阶段                                   │
└─────────────────────────────────────────────────────────────────────────────┘

[subagent_main] (监听 question_queue)
    │
    │ 收到 tool_request 消息
    │ {"type": "tool_request", "task_id": "task_xxx", "tool": {"name": "ppt_generator"}}
    ↓
[call_agent_async]
    │
    │ A2A 调用 pptagent
    ↓
[pptagent]
    │
    │ 生成 PPT (1-2分钟)
    │ 返回 artifact-update 事件
    │ 包含: ```JSONCARD
    │       [{"type": "ppt_result", "id": "41969395", "url": "https://...pptx"}]
    │       ```
    ↓
[subagent_main]
    │
    │ 1. 解析 JSONCARD，缓存到 task_results
    │ 2. 通过 WebSocket 发送消息给前端
    │    {"task_id": "task_xxx", "status": "done", "result_url": "https://...pptx"}
    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                              前端更新阶段                                    │
└─────────────────────────────────────────────────────────────────────────────┘

[TaskCard]
    │
    │ WebSocket onmessage 接收消息
    │ 更新状态: status = "done", result_url = "https://...pptx"
    ↓
[用户点击 TaskCard]
    │
    │ window.open(result_url)
    ↓
[下载 PPT 文件]
```

---

## 关键消息格式

### 1. RabbitMQ tool_request（question_queue）

```json
{
  "type": "tool_request",
  "version": "1.0",
  "task_id": "task_abc123",
  "trace_id": "task_abc123",
  "timestamp": "2025-12-16T14:00:00+08:00",
  "tool": {
    "name": "ppt_generator",
    "args": {
      "paper_id": "41969395"
    }
  }
}
```

### 2. search_agent 返回的 JSONCARD（accepted 状态）

```json
[
  {
    "type": "task",
    "version": "1.0",
    "id": "task_abc123",
    "payload": {
      "tool": "ppt_generator",
      "status": "accepted",
      "progress": 0.0,
      "message": "PPT 生成任务已提交，正在排队处理中。"
    }
  }
]
```

### 3. pptagent 返回的 JSONCARD

```json
[
  {
    "type": "ppt_result",
    "id": "41969395",
    "url": "https://example.com/ppt/41372744_byid_7123c00117a74ceea30e0c12efab88af.pptx"
  }
]
```

### 4. WebSocket 完成消息（subagent_main → 前端）

```json
{
  "task_id": "task_abc123",
  "status": "done",
  "result_url": "https://example.com/ppt/41372744_byid_7123c00117a74ceea30e0c12efab88af.pptx",
  "message": "PPT生成完成，点击查看",
  "result": [
    {
      "type": "ppt_result",
      "id": "41969395",
      "url": "https://example.com/ppt/41372744_byid_7123c00117a74ceea30e0c12efab88af.pptx"
    }
  ]
}
```

---

## 涉及的服务和文件

| 服务 | 关键文件                                     | 作用 |
|------|------------------------------------------|------|
| main_api | `backend/main_api/main.py`               | 前端入口，转发请求到 search_agent |
| search_agent | `backend/search_agent/tools.py`                | 提供 generate_ppt_tool 工具 |
| subagent_main | `backend/subagent_main/main.py`          | 监听任务队列，调用 pptagent |
| pptagent | -                                        | 实际生成 PPT 的服务 |
| 前端 | `frontend/components/cards/TaskCard.tsx` | 显示任务状态和下载链接 |

---

## 通信协议

- **main_api ↔ search_agent**：A2A 协议（HTTP SSE 流式）
- **search_agent ↔ subagent_main**：RabbitMQ（question_queue）
- **subagent_main ↔ pptagent**：A2A 协议（HTTP SSE 流式）
- **subagent_main ↔ 前端**：WebSocket
