# 记忆原理
memory_controller.py 
读取传入的metada中的history，然后拼入event中，作为历史记录
关键使用的代码：
```
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
            session_id,metadata
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

```

# 支持thinking模型，例如Deepseek R1(litellm还不支持，adk已经支持，所以还是会报错)
1. 首先，升级adk为google-adk==1.20
2. 然后处理thought字段
[adk_agent_executor.py](adk_agent_executor.py)
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