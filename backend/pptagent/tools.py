#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/6/20 10:02
# @File  : tools.py.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  :
import os
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool
import time
from datetime import datetime
import requests
import dotenv
import json
import uuid
from datetime import datetime, timezone, timedelta
import asyncio
import logging
from typing import List, Union, Dict, Any, Tuple, Optional
import aiohttp

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

import logging
import os
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools.log"),
    encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))
logger.addHandler(file_handler)

async def generate_ppt_tool(document_id: int, is_english: int = 0) -> str:
    """
    PPT 生成工具
    :param document_id: 文档 ID(等同于paper_id)
    :param is_english: 是否生成英文版，默认是中文 (0: 中文, 1: 英文)
    """
    logger.info(f"调用 generate_ppt_tool: document_id={document_id}, is_english={is_english}")
    try:
         card = [{
            "type": "ppt_result",
            "payload": {"url": "https://cic.tju.edu.cn/faculty/gongxj/course/AI/lectures/C01-Introduction.ppt"}
        }]
         return f"```JSONCARD\n{json.dumps(card, ensure_ascii=False)}\n```"
    except Exception as e:
        logger.exception("generate_ppt_tool failed")
        err_card = [{
            "type": "error",
            "version": "1.0",
            "id": f"error_{uuid.uuid4().hex}",
            "payload": {"message": f"generate_ppt_tool failed: {e}"}
        }]
        return f"```JSONCARD\n{json.dumps(err_card, ensure_ascii=False)}\n```"



async def main():
    papers = await generate_ppt_tool(
        query="ti:\"graph neural network\" AND abs:medical",
    )
    print(papers)


if __name__ == '__main__':
    asyncio.run(main())