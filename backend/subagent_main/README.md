# Sub Agent Main API

子Agent的主函数，用于处理search agent通过tools生成的请求，调用对应的Agent，并提供任务状态查询接口。

## 功能说明

### 核心功能
1. **MQ监听**: 监听来自search agent的tool_request消息
2. **Agent调用**: 根据tool_name调用对应的Agent (translator/ppt_generator)
3. **结果缓存**: 缓存Agent处理结果，等待前端查询
4. **WebSocket接口**: 提供WebSocket连接获取实时任务状态
5. **HTTP接口**: 提供HTTP接口查询任务状态

### 支持的工具类型
- `translator`: 论文翻译工具
- `ppt_generator`: 论文PPT生成工具

## API接口

### WebSocket接口
- **路径**: `/ws/{task_id}`
- **方法**: WebSocket连接
- **功能**: 通过task_id建立WebSocket连接，实时获取任务状态和结果

#### 使用示例
```javascript
const ws = new WebSocket('ws://localhost:10072/ws/task_123');
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('任务状态:', data.status);
    if (data.status === 'completed') {
        console.log('任务结果:', data.result);
    }
};
```

### HTTP接口

#### 查询任务状态
- **路径**: `/task/{task_id}`
- **方法**: GET
- **返回**: 任务状态和结果

#### 健康检查
- **路径**: `/health`
- **方法**: GET
- **返回**: 服务健康状态

## 环境变量配置

需要配置以下环境变量：

```bash
# RabbitMQ配置
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=admin
RABBITMQ_PASSWORD=your_password
RABBITMQ_VIRTUAL_HOST=/

# Agent URL配置
TRANSLATOR_AGENT_URL=http://localhost:10073
PPT_AGENT_URL=http://localhost:10071

# MQ队列配置
QUEUE_NAME_WRITER=question_queue
QUEUE_NAME_READ=answer_queue
```

## 运行方式

### 启动服务
```bash
cd backend/subagent_main
python main.py
```

服务将在 `http://localhost:10072` 启动

### 测试MQ连接
```bash
python test_mq_connection.py
```

## 消息格式

### MQ请求格式 (来自naviagent)
```json
{
  "type": "tool_request",
  "version": "1.0",
  "task_id": "task_xxx",
  "trace_id": "trace_xxx",
  "timestamp": "2025-12-11T10:30:00+08:00",
  "tool": {
    "name": "translator | ppt_generator",
    "args": {}
  }
}
```

### Agent返回格式
期望返回JSONCARD格式的结果：
```jsonCARD
[
  {
    "type": "task | error | ppt_result | translation_result",
    "version": "1.0",
    "id": "result_id",
    "payload": {
      // 具体内容根据工具类型而定
    }
  }
]
```

## 工作流程

1. **search_agent** 调用tools，将tool_request写入MQ的question_queue
2. **subagent_main** 监听MQ，收到tool_request后调用对应Agent
3. **Agent** 处理请求，返回JSONCARD格式结果
4. **subagent_main** 解析结果并缓存，等待前端查询
5. **前端** 通过WebSocket或HTTP接口查询任务状态和结果

## 错误处理

- 如果Agent URL未配置，返回错误结果
- 如果Agent调用失败，返回错误结果
- 如果JSONCARD解析失败，返回格式错误结果
- 所有错误都会缓存到task_results中，前端可以正常获取