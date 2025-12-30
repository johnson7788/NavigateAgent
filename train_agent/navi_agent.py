from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import math
from typing import Any, Dict, List, Optional, cast

import dotenv
from litellm import completion, acompletion

from agentlightning import (
    LLM,
    LitAgent,
    NamedResources,
    Trainer,
    setup_logging,
)
from agents import Agent, Runner
from agents.extensions.models.litellm_model import LitellmModel
from agents.model_settings import ModelSettings
from agents.lifecycle import RunHooks

from tools import (
    translate_paper_tool,
    generate_ppt_tool,
    search_pubmed_tool
)

dotenv.load_dotenv()
setup_logging()

# ============================================================================
# 基础配置
# ============================================================================

TEACHER_API_KEY = os.getenv("TEACHER_API_KEY")
TEACHER_MODEL = os.getenv("TEACHER_MODEL")
TEACHER_BASE_URL = os.getenv("TEACHER_BASE_URL")

if not TEACHER_MODEL.startswith("openai/"):
    TEACHER_MODEL = "openai/deepseek-chat"

# ============================================================================
# 日志：写到本地文件
# ============================================================================

log_file = "nav_agent_training.log"

logger = logging.getLogger("nav_agent_training")
logger.setLevel(logging.INFO)

if not logger.handlers:
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # 同时在控制台打印
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)


# ============================================================================
# Reward 计算
# ============================================================================

NAV_TOOLS = {
    "search_document_db_tool",
    "translate_paper_tool",
    "generate_ppt_tool",
}


# 一个任务内最多多轮对话，最多3轮对话
TRAIN_TURNS = 2
# 多轮对话： 只有在上一轮达到比较好的分数，才开展下一轮的训练
MULTI_TURN_REWARD_THRESHOLD = 3.0

# 导航 Agent 的系统 Prompt
navigation_prompt = """
你是 Medical 的“智能导航与搜索专家”。
你的任务是根据用户需求，精准调用工具查阅文献，或对已有文献进行翻译和PPT生成。
当前日期：2025年12月22日。

### 可用工具
1. **search_pubmed_tool**: 高级医学文献搜索。
2. **translate_paper_tool**: 传入 `paper_id` 翻译指定论文。
3. **generate_ppt_tool**: 传入 `paper_id` 生成论文解读 PPT。

### 核心能力 1: 高级搜索 (search_pubmed_tool)
当用户需要查找文献、临床研究、指南时，**必须**使用此工具。
参数构造规则（严格遵守）：
- **query_string**: 格式为 `("关键词"[字段]) AND/OR (...)`。
  - 字段：`[Title]`, `[Abstract]`, `[Title/Abstract]`, `[MeSH Terms]`, `[Author]`, `[Journal]`。
  - **严禁**：Query 中不能包含日期（年份放 filter），不能包含中文（需翻译为英文），不能直接写单词而不加 `[字段]`。
  - 示例：`("Lung Cancer"[Title]) AND ("Immunotherapy"[Abstract])`
- **filter_string**: 必须以 `$$` 开头，键值对用 `$$` 分隔。
  - 时间：`$$doc_publish_time$$YYYY-MM-DD$$YYYY-MM-DD`
  - 类型：`$$doc_publish_type$$Review` (或 Clinical Trial 等)
  - 示例：`$$doc_publish_time$$2024-01-01$$2025-12-22$$doc_publish_type$$Review`
- **sort_field**: `relevant` (默认), `docPublishTime` (最新), `docIf` (高分), `citedBy` (高引)。

### 核心能力 2: 导航与任务触发
- 如果用户指代“刚才那篇”、“第一篇”、“关于xxx的那篇”，请参考**系统记忆 (System State)** 中的 `paper_id`。
- 如果用户想翻译或做PPT，请直接调用对应工具。

### 你的回答规范
1. 思考用户意图：是搜索？还是针对已知结果的操作？
2. 调用工具。
3. 工具返回后，总结结果（如：发现x篇关于y的文献，核心结论是...）。**不要**原样粘贴 JSON。

"""

# ============================================================================
# Teacher：DeepSeek 负责给导航策略打分
# ============================================================================


class NavigationTeacher:
    @staticmethod
    async def score_navigation_answer(
            question: str,
            final_answer: str,
            tool_calls: List[Dict[str, Any]],
    ) -> float:
        """
        DeepSeek 打分：综合评估工具选择逻辑和最终回答质量
        """
        tool_trace_str = json.dumps(tool_calls, ensure_ascii=False)
        prompt = f"""
你是一个严格的“医学AI助手评估专家”。请对以下对话进行评分 (0.0 - 1.0)。

用户问题: {question}
助手最终回答: {final_answer}
工具调用: {tool_trace_str}

评分标准：
1. **意图识别**: 搜索 vs 翻译 vs PPT，工具选对了吗？
2. **搜索质量**: 如果进行了搜索，Query语法是否专业？Filter是否涵盖了用户的时间/类型限制？。
3. **ID处理**: 如果是翻译/PPT，是否使用了正确的 paper_id？
4. **回答质量**: 总结是否清晰，有无幻觉。

请输出一个浮点数分数，不要解释。

每个工具使用方法：

"""
        try:
            resp = await acompletion(
                model=TEACHER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                api_key=TEACHER_API_KEY,
                base_url=TEACHER_BASE_URL,
                temperature=0.0,
                max_tokens=16,
            )
            content = resp.choices[0].message.content.strip()
            m = re.search(r"(\d+(\.\d+)?)", content)
            if not m:
                return 0.5
            score = float(m.group(1))
            score = max(0.0, min(1.0, score))
            return score
        except Exception as e:
            logger.error(f"[Teacher Error] score_navigation_answer failed: {e}")
            return 0.5

    @staticmethod
    def generate_next_question(history_context: str) -> str:
        """生成下一轮问题，考察多轮对话能力"""
        prompt = f"""
基于历史对话，生成下一个指令。如果刚才搜索了论文，可以改变搜索条件重新搜索或者问新的搜索问题，或者要求挑选一篇论文“翻译”或“做PPT”
历史:
{history_context}

只输出问题文本。
"""
        try:
            resp = completion(
                model=TEACHER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                api_key=TEACHER_API_KEY,
                base_url=TEACHER_BASE_URL,
                temperature=0.7,
                max_tokens=128,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"[Teacher Error] generate_next_question failed: {e}")
            return "请帮我查找一篇关于糖尿病并发症最新治疗进展的文献，并翻译成中文摘要。"

def _extract_jsoncard(raw_result: str) -> Optional[Any]:
    """
    从工具返回的字符串里提取 JSONCARD 的 JSON 对象
    工具返回一般长这样：```JSONCARD\n[ {...} ]\n```
    """
    if not isinstance(raw_result, str):
        return None
    m = re.search(r"```JSONCARD\s*(.*?)\s*```", raw_result, re.S)
    if not m:
        return None
    json_str = m.group(1).strip()
    try:
        return json.loads(json_str)
    except Exception:
        return None
def _collect_paper_ids_from_tool_calls(tool_calls: List[Dict[str, Any]]) -> set[str]:
    """
    从所有 search_document_db_tool 的返回 JSONCARD 中，收集合法的 paper_id 列表
    用于后续检查 translate/ppt 调用是否使用了真实存在的 paper_id
    """
    paper_ids: set[str] = set()
    for c in tool_calls:
        name = c.get("name", "")
        if name != "search_pubmed_tool":
            continue
        result = c.get("result", {})
        raw = result.get("raw_result") or result
        jsoncard = _extract_jsoncard(raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False))
        if not jsoncard:
            continue
        # JSONCARD 可能是 list 或单个 dict
        items = jsoncard if isinstance(jsoncard, list) else [jsoncard]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "paper_result":
                continue
            payload = item.get("payload", {}) or {}
            papers = payload.get("papers", []) or []
            for p in papers:
                pid = str(p.get("paper_id", "")).strip()
                if pid:
                    paper_ids.add(pid)
    return paper_ids

def scale_symmetric_tanh(x: float, max_abs: float) -> float:
    """
    使用 tanh 将任意实数平滑缩放到 [-max_abs, max_abs] 区间。
    不做硬裁剪。
    """
    if max_abs <= 0:
        return 0.0
    # x 越大，越接近 max_abs，但不会被硬截断
    return max_abs * math.tanh(x / max_abs)

def calculate_search_dense_reward(tool_args: dict, tool_result: dict, question: str) -> float:
    """
    计算搜索工具的稠密奖励（从 rag_agent.py 完整迁移并适配）
    """
    reward = 0.0
    logs = []

    # --- 1. 数据预处理 ---
    # navi_agent 的 result 结构通常是 {"raw_result": "..."} 或直接是 dict
    raw_res = tool_result.get("raw_result") if isinstance(tool_result, dict) else tool_result

    # 尝试解析 API 返回结果以获取 code 和 records
    api_code = 500
    api_records = []
    api_msg = ""

    try:
        if isinstance(raw_res, str):
            # 尝试提取 JSONCARD 或直接解析 JSON
            card = _extract_jsoncard(raw_res)
            if card:
                # 假设 JSONCARD 返回的是 list，取第一个
                item = card[0] if isinstance(card, list) and card else card
                # 注意：实际工具返回结构可能不同，这里假设标准结构
                # 如果是 search_pubmed_tool，通常直接返回 JSON 字符串
                if isinstance(item, dict):
                    # 适配：有时 JSONCARD payload 才是真实数据，有时外层就是
                    pass

                    # 再次尝试直接解析 JSON (search_pubmed_tool 通常返回 raw json string)
            if not card:
                parsed = json.loads(raw_res)
                api_code = parsed.get("code", 200)  # 默认为200如果解析成功
                api_records = parsed.get("records", [])
                api_msg = parsed.get("msg", "")
        elif isinstance(raw_res, dict):
            api_code = raw_res.get("code", 200)
            api_records = raw_res.get("records", [])
            api_msg = raw_res.get("msg", "")
    except Exception:
        pass

    # 提取参数
    q_str = tool_args.get("query_string", "")
    f_str = tool_args.get("filter_string", "")
    sort_field = tool_args.get("sort_field", "relevant")

    # 定义常量
    valid_tags_list = ["Title", "Abstract", "MeSH Terms", "Author", "Journal", "Title/Abstract"]
    article_types = [
        "Meta-Analysis", "Clinical Study", "Clinical Trial",
        "Systematic Review", "Randomized Controlled Trial", "Review",
    ]

    # =========================================================
    # 2. 语法微观奖励 (Micro Syntax Rewards)
    # =========================================================

    # [Check] 空值检查
    if not q_str:
        return -3.0

    # Query 长度
    q_len = len(q_str)
    if 5 <= q_len <= 100:
        reward += 0.5
    elif q_len > 100:
        reward -= 0.8  # 太长

    # 中文检测
    if re.search(r"[\u4e00-\u9fff]", q_str):
        reward -= 1.5
    else:
        reward += 0.3

    # 逻辑复杂度
    logic_count = q_str.count(" AND ") + q_str.count(" OR ") + q_str.count(" NOT ")
    if logic_count == 0:
        reward += 0.3
    elif logic_count > 1:
        reward -= 0.5 * logic_count

    # 字段限定符 [...]
    tags = re.findall(r"\[(.*?)\]", q_str)
    if tags:
        reward += 0.3
        # 检查 Tag 内容合法性
        valid_count = sum(1 for t in tags if t in valid_tags_list)
        if valid_count == len(tags):
            reward += 0.5
        else:
            reward -= 0.2
    else:
        reward -= 1.0  # 没写字段

    # 括号平衡
    if q_str.count('(') == q_str.count(')') and q_str.count('(') > 0:
        reward += 0.2
    elif q_str.count('(') != q_str.count(')'):
        reward -= 0.5

    # [Rule] 日期严禁出现在 Query 中
    if re.search(r"\b(19|20)\d{2}\b", q_str):
        reward -= 1.0

    # [Rule] 文章类型严禁出现在 Query 中
    q_lower = q_str.lower()
    types_in_query = [t for t in article_types if t.lower() in q_lower]
    if types_in_query:
        reward -= 1.5

    # =========================================================
    # 3. Filter 逻辑检查
    # =========================================================
    f_lower = f_str.lower() if f_str else ""

    if f_str:
        if f_str.startswith("$$"):
            reward += 0.5
        else:
            reward -= 1.0

        # 日期数量检查
        date_pattern = r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b"
        date_matches = re.findall(date_pattern, f_str)

        if "doc_publish_time" in f_str:
            if len(date_matches) == 2:
                reward += 0.7
            else:
                reward -= 1.0  # 必须起止两个日期
        elif len(date_matches) > 0:
            # 有日期但没用 doc_publish_time 字段
            reward -= 0.5

        # 文章类型在 Filter 中出现 -> 奖励
        types_in_filter = [t for t in article_types if t.lower() in f_lower]
        if types_in_filter:
            reward += 0.2

    # =========================================================
    # 4. API 执行结果反馈
    # =========================================================
    if api_code == 200:
        reward += 2.0
        if len(api_records) > 0:
            reward += 1.0
        else:
            reward -= 0.1  # 无结果
    elif api_code == 400:
        reward -= 1.5
    elif api_code == 500:
        reward -= 0.1

    # =========================================================
    # 5. 意图对齐 (Intent Alignment)
    # =========================================================
    if reward > -2.0:  # 基础格式太差就不看意图了
        user_q_lower = question.lower()

        # 时间意图
        time_keywords = ["2024", "2025", "最新", "latest", "recent", "newest"]
        if any(k in user_q_lower for k in time_keywords):
            # 检查 filter 或 sort_field
            if "doc_publish_time" in f_str or "docPublishTime" in sort_field:
                reward += 0.8
            else:
                reward -= 0.4

        # 综述意图
        if "综述" in question or "review" in user_q_lower:
            if "Review" in f_str or "Meta-Analysis" in f_str:
                reward += 0.8
            else:
                reward -= 0.4

        # RCT 意图
        if any(k in user_q_lower for k in ["rct", "randomized", "trial", "临床试验"]):
            if "doc_publish_type" in f_str and (
                    "randomized" in f_lower or "clinical trial" in f_lower
            ):
                reward += 0.8
            else:
                reward -= 0.4

    # 限制范围
    return scale_symmetric_tanh(reward, 5.0)


async def compute_navigation_reward(
        question: str,
        final_answer: str,
        tool_calls: List[Dict[str, Any]],
) -> float:
    """
    导航智能体的奖励函数（增强版）

    构成：
    1. Teacher 总分           -> 主体 (0~4)
    2. 工具匹配奖励           -> 与任务类型匹配
    3. paper_id 合法性/一致性 -> 来自搜索结果、可转成数字
    4. JSONCARD 输出检查      -> 最终回答里是否插入 JSONCARD
    5. 工具使用效率/必要性    -> 不乱调工具、不滥用
    6. 幻觉工具惩罚          -> 使用未知工具名
    """
    base_reward = 0.0

    # 1. Intent Detection
    q_lower = question.lower()
    has_trans = "翻" in question or "translate" in q_lower
    has_ppt = "ppt" in q_lower or "演示" in question
    has_search = not (has_trans or has_ppt)  # 简化逻辑：不是后处理就是搜索

    used_tools = [c.get("name") for c in tool_calls]
    used_tools_set = set(used_tools)

    # 2. Tool Match Reward
    if has_trans:
        if "translate_paper_tool" in used_tools_set:
            base_reward += 1.0
        else:
            base_reward -= 1.0
    elif has_ppt:
        if "generate_ppt_tool" in used_tools_set:
            base_reward += 1.0
        else:
            base_reward -= 1.0
    else:
        # Search intent
        if "search_pubmed_tool" in used_tools_set:
            base_reward += 1.0
            # 这里叠加 Dense Reward
            for c in tool_calls:
                if c["name"] == "search_pubmed_tool":
                    # 调用针对搜索参数的评分
                    search_r = calculate_search_dense_reward(c["args"], c["result"], question)
                    base_reward += search_r
        else:
            base_reward -= 1.0

    # 3. Paper ID Validity (如果用了 Trans/PPT)
    valid_ids = _collect_paper_ids_from_tool_calls(tool_calls)  # 从历史或当前轮次
    # 注意：这里有个问题，valid_ids 只能拿到当前轮的。如果是多轮，应该从 history 里拿。
    # 简化处理：检查格式是否像 ID
    for c in tool_calls:
        if c["name"] in ["translate_paper_tool", "generate_ppt_tool"]:
            pid = c["args"].get("paper_id", "")
            if pid and (pid.isdigit() or len(pid) > 4):  # 简单校验
                base_reward += 0.5
            else:
                base_reward -= 1.0

    # 4. Teacher Score
    t_score = await NavigationTeacher.score_navigation_answer(question, final_answer, tool_calls)
    base_reward += (t_score * 3.0)

    # 5. Penalties
    if "```JSONCARD" in final_answer:
        base_reward -= 1.0  # 泄露内部协议

    return scale_symmetric_tanh(base_reward, 5.0)


# ============================================================================
# Hook & State Management
# ============================================================================

def _collect_papers_state(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """提取搜索结果，构建 Nav State"""
    state = []
    for c in tool_calls:
        if c.get("name") != "search_pubmed_tool": continue
        res = c.get("result", {})
        raw = res.get("raw_result") if isinstance(res, dict) else res
        card = _extract_jsoncard(str(raw))
        if not card: continue

        items = card if isinstance(card, list) else [card]
        for item in items:
            papers = item.get("payload", {}).get("papers", [])
            for idx, p in enumerate(papers, 1):
                state.append({
                    "idx": idx,  # 方便用户说 "第一篇"
                    "paper_id": p.get("paper_id"),
                    "title": p.get("title"),
                    "year": p.get("publish_time", "")[:4]
                })
    return state


class NavHooks(RunHooks[Any]):
    def __init__(self):
        self.tool_calls = []

    async def on_tool_end(self, context, agent, tool, result: str):
        try:
            args = json.loads(context.tool_arguments)
        except:
            args = {"raw": context.tool_arguments}
        self.tool_calls.append({
            "name": getattr(tool, "name", "unknown"),
            "args": args,
            "result": {"raw_result": result}
        })


# ============================================================================
# Agent Implementation
# ============================================================================

class NavSearchAgent(LitAgent[Any]):
    def __init__(self, trained_agents=None):
        super().__init__(trained_agents=trained_agents)

    async def training_rollout_async(self, task: Any, rollout_id: str, resources: NamedResources,
                                     model_prefix="hosted_vllm/") -> Any:
        llm = cast(LLM, resources.get("main_llm"))
        question = task.get("question", "")
        history = []
        total_reward = 0.0
        nav_state = []  # 全局状态

        # Tools
        tools = [search_pubmed_tool, translate_paper_tool, generate_ppt_tool]

        for turn in range(TRAIN_TURNS):
            logger.info(f"--- Turn {turn + 1} Q: {question} ---")

            # 构造输入：包含 Nav State
            state_str = ""
            if nav_state:
                state_str = f"SYSTEM_STATE (Only for you): {json.dumps(nav_state, ensure_ascii=False)}\n"

            # 拼接 Prompt
            history_text = "\n".join(history)
            full_input = f"{state_str}History:\n{history_text}\nUser: {question}"

            hooks = NavHooks()
            agent = Agent(
                model=LitellmModel(model=model_prefix + llm.model, base_url=llm.endpoint, api_key=llm.api_key),
                model_settings=ModelSettings(max_tokens=2048, temperature=0.7),
                name="NavSearchStudent",
                instructions=navigation_prompt,
                tools=tools
            )

            try:
                # 运行
                res = await Runner.run(agent, full_input, max_turns=4, hooks=hooks)
                ans = res.final_output
            except Exception as e:
                logger.error(f"Run failed: {e}")
                ans = "Error"

            # 更新状态
            new_state = _collect_papers_state(hooks.tool_calls)
            if new_state:
                nav_state = new_state  # 更新当前看到的论文
                history.append(f"SYSTEM: Search returned {len(new_state)} papers.")

            # 记录历史
            history.append(f"User: {question}")
            history.append(f"Assistant: {ans}")

            # 计算奖励
            r = await compute_navigation_reward(question, ans, hooks.tool_calls)
            total_reward += r
            logger.info(f"Turn Reward: {r}")

            # 只有当本轮奖励达到“比较好”的阈值时，才进行下一轮对话
            if r >= MULTI_TURN_REWARD_THRESHOLD and turn < TRAIN_TURNS - 1:
                question = NavigationTeacher.generate_next_question("\n".join(history))
            else:
                # 奖励不够好或已经是最后一轮，提前结束多轮对话
                logger.info(
                    f"Stop multi-turn: reward={r:.3f}, "
                    f"threshold={MULTI_TURN_REWARD_THRESHOLD}, turn={turn + 1}"
                )
                break
        return total_reward

    async def validation_rollout_async(
            self,
            task: Any,
            rollout_id: str,
            resources: NamedResources,
    ) -> Any:
        llm: LLM = cast(LLM, resources.get("main_llm"))
        resources = {
            "main_llm": LLM(
                endpoint=llm.endpoint,
                model=llm.model,
                api_key=llm.api_key,
                sampling_parameters={"temperature": 0.7},
            )
        }
        return await self.training_rollout_async(task, rollout_id, resources)


if __name__ == "__main__":
    Trainer(n_workers=12).fit_v0(NavSearchAgent(), "http://localhost:9999/")