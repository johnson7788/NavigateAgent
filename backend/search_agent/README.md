# 搜索Agent

> 本项目提供智能搜索功能

## 记忆原理

`memory_controller.py` 负责读取传入的metadata中的history，并将其拼入event中作为历史记录使用。

### 关键代码示例

```python
## Step1，导入
from memory_controller import MemoryController

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ADKAgentExecutor(AgentExecutor):
    """An AgentExecutor that runs an ADK-based Agent."""

    def __init__(self, runner: Runner, card: AgentCard, run_config):
        self.runner = runner
        self._card = card

        self._running_sessions = {}
        self.run_config = run_config
        # Step2，初始化
        self.memory_controller = MemoryController(runner)

    async def _process_request(
        self,
        new_message: types.Content,
        session_id: str,
        task_updater: TaskUpdater,
        metadata: dict | None = None
    ) -> None:
        # The call to self._upsert_session was returning a coroutine object,
        # leading to an AttributeError when trying to access .id on it directly.
        # We need to await the coroutine to get the actual session object.
        # metadata用户传入的原数据
        session_obj = await self._upsert_session(
            session_id, metadata
        )
        logger.debug(f"收到请求信息: {new_message}")
        # Update session_id with the ID from the resolved session object
        # to be used in self._run_agent.
        session_id = session_obj.id
        # 在 agent 运行之前，将 metadata 中的 history 写入 memory service
        # Step3，使用
        if metadata:
            await self.memory_controller.inject_history_from_metadata(session_obj, metadata)
        async for event in self._run_agent(session_id, new_message):
            ...
```

## 支持Thinking模型

支持Thinking模型（例如Deepseek R1）。注意：litellm尚不支持，但ADK已支持。

### 配置步骤

1. 首先升级ADK版本：
   ```bash
   pip install google-adk==1.20
   ```

2. 然后处理thought字段，参考 `adk_agent_executor.py`：

```python
# 检查是否包含文本 (Gemini 的 thought 内容也是放在 text 字段里的)
def convert_genai_part_to_a2a(part: types.Part) -> Part:
    """Convert a single Google Gen AI Part type into an A2A Part type."""
    # 检查是否包含文本 (Gemini 的 thought 内容也是放在 text 字段里的)
    if part.text:
        # 获取 thought 属性，默认为 False
        is_thought = getattr(part, "thought", False)

        # 假设 TextPart 支持 metadata 参数
        # 如果不支持，请检查 a2a.types.TextPart 的定义
        metadata = {"thought": True} if is_thought else {}
        return TextPart(text=part.text, metadata=metadata)
    if part.file_data:
        ...
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `agent.py` | Agent主逻辑 |
| `tools.py` | 工具函数集合 |
| `main_api.py` | API接口服务 |
| `prompt.py` | 提示词模板 |
| `memory_controller.py` | 记忆控制器 |
| `create_model.py` | 模型创建工具 |
| `a2a_client.py` | A2A客户端 |
| `adk_agent_executor.py` | ADK执行器 |
| `cache_utils.py` | 缓存工具 |
| `requirements.txt` | 依赖包列表 |
| `.env` | 环境变量配置 |

## 环境配置

1. 复制 `env_template.txt` 为 `.env`
2. 配置必要的环境变量

## 依赖安装

```bash
pip install -r requirements.txt
```

## 运行服务

```bash
python main_api.py
```
