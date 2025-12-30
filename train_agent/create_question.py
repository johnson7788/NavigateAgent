#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/12/18 15:15
# @File  : only_question.py
# @Author: johnson
# @Contact :
# @Desc  : 使用 LLM 基于种子话题批量生成“导航智能体”用户问题数据

import asyncio
import json
import uuid
import pandas as pd
import os
import logging
import random
from typing import List
from dotenv import load_dotenv

# 引入 OpenAI 客户端
from openai import AsyncOpenAI

# ==========================================
# 1. 配置区域
# ==========================================

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL")

OUTPUT_DIR = "data"
TRAIN_FILE = "train.parquet"
DEV_FILE = "val.parquet"
TOPIC_FILE = "data/seed_topic.txt"

# 这里依然用固定答案，占位，真实训练时模型学“动态回答这4个字”
FIXED_ANSWER = "动态回答"

TARGET_COUNT = 1000  # 目标生成数量
CONCURRENCY_LIMIT = 20  # 并发请求数量，根据你的API配额调整

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DataBuilder")


# ==========================================
# 2. 辅助函数
# ==========================================

def load_seed_topics(file_path: str) -> List[str]:
    """从文本文件加载种子话题，每行一个"""
    with open(file_path, 'r', encoding='utf-8') as f:
        topics = [line.strip() for line in f if line.strip()]

    assert len(topics), "没有加载种子话题！"
    logger.info(f"✅ 成功从 {file_path} 加载了 {len(topics)} 个种子话题。")
    return topics


# ==========================================
# 3. LLM 交互模块
# ==========================================

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)

    async def generate_question(self, topic: str, intent: str) -> str:
        """
        根据 Topic + 意图 生成一个“面向 Navi Agent 的用户问题”。

        intent 取值：
        - search             -> 只想搜索内部数据库
        - translate_title    -> 想翻译某篇论文，用户给出论文题目/大致描述（无 id）
        - translate_context  -> 想翻译某篇论文，用户用“这篇/刚才那篇”等上下文指代（无 id）
        - ppt_title          -> 想生成 PPT，用户给出论文题目/大致描述（无 id）
        - ppt_context        -> 想生成 PPT，用户用“这篇/刚才那篇”等上下文指代（无 id）
        """

        if intent == "search":
            instruction = f"""
你现在扮演导航智能体 Navi Agent 的真实用户。

请围绕主题 "{topic}"，生成一个**中文问题**，目的是让助手帮你在「内部数据库」里**检索/搜索相关论文或资料**。

要求：
1. 问句自然、口语化，像医生或科研人员真的会问的那种。
2. 问题中要明确表现出“想搜索/查找文献、资料、论文”等意图，比如“帮我查查…文献”“找几篇…相关的论文”等。
3. 不要提到“工具”“接口”“系统”“Navi Agent”等内部概念。
4. 不要输出任何解释性文字，只生成一个问题句子。

返回格式 JSON：
{{
  "question": "用户会说的那一句话"
}}
"""

        elif intent == "translate_title":
            instruction = f"""
你现在扮演导航智能体的真实用户。

请围绕主题 "{topic}"，生成一个**中文请求**，目的是让助手帮你**翻译一篇英文论文**，
用户手里掌握这篇论文的大致题目或内容描述，会在问题里说出来。

要求：
1. 问句自然、口语化，像科研人员在跟助手说话。
2. 需要在句子里提到论文的大致题目或内容，比如：
   - “题目大概是《……》”
   - “关于……的一篇英文论文”
3. 绝对不要出现任何形式的 id、paper_id、编号（比如 id=123、paper_id=xxx 之类都不要出现）。
4. 问题语气要明确是在请求“翻译这篇论文”。
5. 不要提到“工具”“接口”“系统”“Navi Agent”等内部概念。
6. 不要输出示例或说明，只生成这一个问题句子。

返回格式 JSON：
{{
  "question": "用户会说的那一句话"
}}
"""

        elif intent == "translate_context":
            instruction = f"""
你现在扮演导航智能体的真实用户。

请围绕主题 "{topic}"，生成一个**中文请求**，目的是让助手帮你**翻译某篇论文**，
但用户不再重复论文题目，而是用上下文指代，比如“这篇论文”“刚才你帮我找到的那篇”“列表里的第二篇”等。

要求：
1. 问句自然、口语化，假设这句话出现在一次对话的**后续轮次**。
2. 需要用类似下面的表达进行指代：
   - “把刚才你帮我查到的那篇关于……的论文翻译一下”
   - “能帮我把列表里第二篇论文翻成中文吗”
   - “把这篇英文原文全文翻译成中文”
3. 绝对不要出现任何形式的 id、paper_id、编号（比如 id=123、paper_id=xxx 之类）。
4. 不要提到“工具”“接口”“系统”“Navi Agent”等内部概念。
5. 不要输出示例或说明，只生成这一个问题句子。

返回格式 JSON：
{{
  "question": "用户会说的那一句话"
}}
"""

        elif intent == "ppt_title":
            instruction = f"""
你现在扮演导航智能体的真实用户。

请围绕主题 "{topic}"，生成一个**中文请求**，目的是让助手帮你**根据一篇论文生成 PPT/汇报幻灯片**，
用户会给出这篇论文的大致题目或内容描述。

要求：
1. 问句自然、口语化，像医生/科研人员准备组会汇报或答辩时说的话。
2. 在句子里提到论文的题目或内容描述，比如：
   - “题目是《……》的一篇论文”
   - “一篇关于……的英文论文”
3. 可以顺带提 PPT 的用途（组会/汇报/分享会等），但不要太长。
4. 绝对不要出现任何形式的 id、paper_id、编号。
5. 不要提到“工具”“接口”“系统”“Navi Agent”等内部概念。
6. 不要输出示例或说明，只生成这一个问题句子。

返回格式 JSON：
{{
  "question": "用户会说的那一句话"
}}
"""

        elif intent == "ppt_context":
            instruction = f"""
你现在扮演导航智能体的真实用户。

请围绕主题 "{topic}"，生成一个**中文请求**，目的是让助手帮你**把之前查到的某篇论文生成 PPT/汇报幻灯片**，
用户不再重复论文题目，而是用“刚才那篇”“列表里的第三篇”“这篇论文”等进行指代。

要求：
1. 问句自然、口语化，假设这句话出现在一次对话的**后续轮次**。
2. 需要用类似下面的表达进行指代（自己发挥，不要照抄示例用语）：
   - “把刚才你找到的那篇关于……的论文做成 PPT”
   - “能帮我把列表里第三篇论文整理成一个汇报吗”
   - “用这篇论文帮我做一个适合组会的 PPT”
3. 可以简单说明 PPT 用途（比如组会汇报、开题答辩等），但不要太长。
4. 绝对不要出现任何形式的 id、paper_id、编号。
5. 不要提到“工具”“接口”“系统”“Navi Agent”等内部概念。
6. 不要输出示例或说明，只生成这一个问题句子。

返回格式 JSON：
{{
  "question": "用户会说的那一句话"
}}
"""

        else:
            # 回退到搜索意图
            instruction = f"""
你现在扮演导航智能体的真实用户。

请围绕主题 "{topic}"，生成一个**中文问题**，目的是让助手帮你在「内部数据库」里**检索/搜索相关论文或资料**。

返回格式 JSON：
{{
  "question": "用户会说的那一句话"
}}
"""

        try:
            response = await self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": instruction}],
                response_format={"type": "json_object"},
                temperature=0.8  # 增加随机性，保证多样化
            )
            content = response.choices[0].message.content
            res_json = json.loads(content)
            return res_json.get("question", "").strip()
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return ""


# ==========================================
# 4. 核心构建流程
# ==========================================

class DataPipeline:
    def __init__(self):
        self.llm = LLMClient()
        self.topics = load_seed_topics(TOPIC_FILE)
        self.data_store = []
        # 使用信号量控制并发数
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    def _sample_intent(self) -> str:
        """
        随机采样一个意图：
        大致比例（你可以按需改）：
        - 搜索：60%
        - 翻译(基于标题/内容描述)：15%
        - 翻译(上下文指代)：5%
        - PPT(基于标题/内容描述)：15%
        - PPT(上下文指代)：5%
        """
        intents = [
            "search",
            "translate_title",
            "translate_context",
            "ppt_title",
            "ppt_context",
        ]
        weights = [0.6, 0.15, 0.05, 0.15, 0.05]
        return random.choices(intents, weights=weights, k=1)[0]

    async def process_one_sample(self, idx: int):
        """处理单个样本生成的任务"""
        async with self.semaphore:
            topic = random.choice(self.topics)
            intent = self._sample_intent()

            try:
                question = await self.llm.generate_question(topic, intent)
                if not question:
                    return

                # 构造数据
                entry = {
                    "id": f"med_nav_{uuid.uuid4().hex[:8]}",
                    "question": question,
                    "answer": FIXED_ANSWER
                    # 如果以后要训练 Router，可以在这里加 "intent": intent
                }

                self.data_store.append(entry)

                # 每生成 50 条打印一次进度
                if len(self.data_store) % 50 == 0:
                    logger.info(f"⚡ 已生成 {len(self.data_store)} 条数据...")

            except Exception as e:
                logger.error(f"Sample {idx} error: {e}")

    async def run(self, num_samples=1000):
        logger.info(f"开始构建数据，目标生成数量: {num_samples}，并发数: {CONCURRENCY_LIMIT}")

        # 创建所有任务
        tasks = [self.process_one_sample(i) for i in range(num_samples)]

        # 并发执行
        await asyncio.gather(*tasks)

        logger.info(f"任务结束，实际生成有效数据: {len(self.data_store)} 条")

    def save(self):
        if not self.data_store:
            logger.warning("没有生成数据，跳过保存。")
            return

        df = pd.DataFrame(self.data_store)

        # 确保只保留需要的列
        cols = ["id", "question", "answer"]
        df = df[cols]

        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

        # 简单的 Train/Val 划分 (9:1)
        if len(df) > 10:
            df_val = df.sample(frac=0.1, random_state=42)
            df_train = df.drop(df_val.index)
        else:
            df_train = df
            df_val = df.iloc[0:0]

        train_path = os.path.join(OUTPUT_DIR, TRAIN_FILE)
        val_path = os.path.join(OUTPUT_DIR, DEV_FILE)

        df_train.to_parquet(train_path, index=False)
        df_val.to_parquet(val_path, index=False)

        logger.info(f"✅ 保存训练集: {len(df_train)} 条 -> {train_path}")
        logger.info(f"✅ 保存验证集: {len(df_val)} 条 -> {val_path}")


# ==========================================
# 5. 主程序入口
# ==========================================

async def main():
    pipeline = DataPipeline()
    # 生成 TARGET_COUNT 条
    await pipeline.run(num_samples=TARGET_COUNT)
    pipeline.save()


if __name__ == "__main__":
    asyncio.run(main())
