#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/6/20 10:02
# @File  : tools.py.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  :
import os
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
from agents import function_tool
dotenv.load_dotenv()

logger = logging.getLogger(__name__)

def build_simple_tool_request(
    tool_name: str,
    args: Dict[str, Any],
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    构造你定义的极简 MQ 消息：
    {
      type, version, task_id, trace_id, timestamp, tool:{name,args}
    }
    """
    task_id = f"task_{uuid.uuid4().hex}"
    trace_id = trace_id or task_id

    tz = timezone(timedelta(hours=8))  # +08:00
    timestamp = datetime.now(tz).isoformat()

    return {
        "type": "tool_request",
        "version": "1.0",
        "task_id": task_id,
        "trace_id": trace_id,
        "timestamp": timestamp,
        "tool": {
            "name": tool_name,
            "args": args
        }
    }


# @function_tool
async def search_pubmed_tool(
    query_string: str,
    sort_field: str = "relevance",
    page_num: int = 1,
    page_size: int = 5,
) -> Dict[str, Any]:
    """
    使用 PubMed E-utilities 搜索文献
    """
    NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    NCBI_DB = "pubmed"
    retstart = (page_num - 1) * page_size

    async with aiohttp.ClientSession() as session:
        # 1. ESearch：获取 PMID 列表
        search_params = {
            "db": NCBI_DB,
            "term": query_string,
            "retmode": "json",
            "retstart": retstart,
            "retmax": page_size,
            "sort": "relevance" if sort_field == "relevant" else "pub+date",
        }

        async with session.get(f"{NCBI_BASE}/esearch.fcgi", params=search_params) as resp:
            search_data = await resp.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return {"code": 200, "records": []}

        # 2. EFetch：拉取文献详情
        fetch_params = {
            "db": NCBI_DB,
            "id": ",".join(id_list),
            "retmode": "xml",
        }

        async with session.get(f"{NCBI_BASE}/efetch.fcgi", params=fetch_params) as resp:
            xml_text = await resp.text()

    # 3. 解析 XML（简单示例）
    from xml.etree import ElementTree as ET

    root = ET.fromstring(xml_text)
    records = []

    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID")
        title = article.findtext(".//ArticleTitle")
        abstract = " ".join(
            [x.text or "" for x in article.findall(".//AbstractText")]
        )
        journal = article.findtext(".//Journal/Title")
        pub_date = article.findtext(".//PubDate/Year")

        records.append({
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "journal": journal,
            "publish_date": pub_date,
            "authors": "",  # 可扩展
            "impact_factor": ""
        })

    return {
        "code": 200,
        "records": records
    }



@function_tool
async def translate_paper_tool(
    paper_id: Optional[str] = None,
    target_lang: str = "zh-CN",
) -> str:
    """
    论文翻译工具（长任务，异步函数）,
    paper_id是搜索到的论文的id
    target_lang：默认翻译成中文
    """
    if not paper_id:
        err_card = [
            {
                "type": "error",
                "version": "1.0",
                "id": f"error_{uuid.uuid4().hex}",
                "payload": {"message": "translate_paper_tool requires paper_id"}
            }
        ]
        return f"```JSONCARD\n{json.dumps(err_card, ensure_ascii=False)}\n```"

    args = {
        "paper_id": paper_id,
        "target_lang": target_lang
    }

    req_msg = build_simple_tool_request(
        tool_name="translator",
        args=args,
    )

    task_id = req_msg["task_id"]

    accepted_card = [
        {
            "type": "task",
            "version": "1.0",
            "id": task_id,
            "payload": {
                "tool": "translator",
                "status": "accepted",
                "progress": 0.0,
                "message": "翻译任务已提交，正在排队处理中。",
            }
        }
    ]
    return f"```JSONCARD\n{json.dumps(accepted_card, ensure_ascii=False)}\n```"

@function_tool
async def generate_ppt_tool(
    paper_id: Optional[str] = None,
) -> str:
    """
    PPT 生成工具（长任务，异步函数）
    paper_id是搜索到的论文的id
    """
    if not paper_id:
        err_card = [
            {
                "type": "error",
                "version": "1.0",
                "id": f"error_{uuid.uuid4().hex}",
                "payload": {"message": "generate_ppt_tool requires paper_id"}
            }
        ]
        return f"```JSONCARD\n{json.dumps(err_card, ensure_ascii=False)}\n```"

    args = {
        "paper_id": paper_id,
    }
    req_msg = build_simple_tool_request(
        tool_name="ppt_generator",
        args=args,
    )

    task_id = req_msg["task_id"]

    accepted_card = [
        {
            "type": "task",
            "version": "1.0",
            "id": task_id,
            "payload": {
                "tool": "ppt_generator",
                "status": "accepted",
                "progress": 0.0,
                "message": "PPT 生成任务已提交，正在排队处理中。",
            }
        }
    ]
    return f"```JSONCARD\n{json.dumps(accepted_card, ensure_ascii=False)}\n```"


async def main():
    # 需要注释掉@function_tool，然后运行这个main
    contents = await search_pubmed_tool(query_string="diabetes")
    print(contents)
    # 翻译
    # jsoncard_str = await translate_paper_tool(paper_id="123456")
    # print(jsoncard_str)
    # # 生成 PPT
    # jsoncard_str = await generate_ppt_tool(paper_id="abcd1234")
    # print(jsoncard_str)


if __name__ == '__main__':
    asyncio.run(main())