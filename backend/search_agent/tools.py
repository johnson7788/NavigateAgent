#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/12/8 11:52
# @File  : mcp_search.py
# @Author: johnson
# @Desc    : 搜索接口 MCP 版 (带输入校验)

import asyncio
import logging
import re  # 引入正则进行格式校验
from enum import Enum
import aiohttp
import os
import time
from datetime import datetime
import requests
import dotenv
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Union, Dict, Any, Tuple, Optional
import pika
from pika.exceptions import AMQPConnectionError
dotenv.load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# RabbitMQ Configuration from environment variables
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USERNAME = os.getenv("RABBITMQ_USERNAME", "admin")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "welcome")
RABBITMQ_VIRTUAL_HOST = os.getenv("RABBITMQ_VIRTUAL_HOST", "/")
# 从哪个队列中读取数据,写入到问题，从答案读取
QUEUE_NAME_WRITER = os.getenv("QUEUE_NAME_WRITER", "question_queue")
QUEUE_NAME_READ = os.getenv("QUEUE_NAME_READ", "answer_queue")
logger.info(f"连接 RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}, user: {RABBITMQ_USERNAME}")

def get_rabbitmq_connection():
    """Creates and returns a new RabbitMQ connection."""
    credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VIRTUAL_HOST,
        credentials=credentials,
        heartbeat=600
    )
    try:
        return pika.BlockingConnection(parameters)
    except AMQPConnectionError as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        raise

def publish_to_question_queue(final_body: str):
    """发送消息"""
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME_WRITER, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME_WRITER,
            body=final_body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        connection.close()
        logger.info(f"发送消息成功到队列 {QUEUE_NAME_WRITER} 发送消息为: {final_body}")
    except AMQPConnectionError as e:
        # Re-raise to be caught in the endpoint
        raise e

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


async def translate_paper_tool(
    paper_id: Optional[str] = None,
    target_lang: str = "zh-CN",
) -> str:
    """
    论文翻译工具（长任务，异步函数）
    - 需要文献的paper_id
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

    publish_to_question_queue(json.dumps(req_msg, ensure_ascii=False))
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


async def generate_ppt_tool(
    paper_id: Optional[str] = None,
) -> str:
    """
    PPT 生成工具（长任务，异步函数）
    - 需要文献的paper_id
    - 立即返回 accepted task JSONCARD
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

    publish_to_question_queue(json.dumps(req_msg, ensure_ascii=False))
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


# -----------------------------------------------------------------------------
# 1. 定义常量和枚举 (保持不变)
# -----------------------------------------------------------------------------

class SearchField(Enum):
    """
    Keywords 搜索支持的字段标签， 使用filter中的日期，就用不keywords中的日期了
    """
    TITLE = "Title"
    MESH_TERMS = "MeSH Terms"
    TITLE_ABSTRACT = "Title/Abstract"
    AUTHOR = "Author"
    ABSTRACT = "Abstract"
    JOURNAL = "Journal"
    AFFILIATION = "Affiliation"
    FIRST_AUTHOR = "First Author"
    LAST_AUTHOR = "Last Author"
    FIRST_AUTHOR_AFFILIATION = "First Author Affiliation"
    LAST_AUTHOR_AFFILIATION = "Last Author Affiliation"
    CORPORATE_AUTHOR = "Corporate Author"


class LogicOp(Enum):
    """逻辑运算符"""
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class SortType(Enum):
    """
    排序规则
    """
    IF = "docIf"  # IF权重
    PUBLISH_TIME = "docPublishTime"  # 发布时间
    CITED_BY = "citedBy"  # 引用数量
    Relevant = "relevant"  # 相关性

# -----------------------------------------------------------------------------
# 3. 查询构造器 & 筛选构造器 (保持不变，省略以节省空间，实际代码中请保留)
# -----------------------------------------------------------------------------
class QueryBuilder:
    """
    用于构建复杂的 keywords 查询字符串
    """

    @staticmethod
    def term(value: str, field: Union[SearchField, str] = None) -> str:
        """
        创建一个带标签的术语
        示例: "肺癌"[Title] 或 "Lung Cancer"
        """
        clean_val = str(value).replace('"', '\\"')  # 简单转义防止破坏格式
        field_str = field.value if isinstance(field, SearchField) else field

        if field_str:
            return f'"{clean_val}"[{field_str}]'
        return f'"{clean_val}"'

    @staticmethod
    def combine(items: List[str], operator: LogicOp = LogicOp.AND) -> str:
        """
        将多个查询部分用逻辑符连接。
        要求: 每个子条件单独用括号包裹:
          ("Lung Cancer"[Title]) OR ("Immunotherapy"[Abstract])
        """
        if not items:
            return ""

        valid_items: List[str] = []
        for item in items:
            if not item:
                continue
            s = item.strip()
            # 如果已经是以括号包住的，不重复包
            if s.startswith("(") and s.endswith(")"):
                valid_items.append(s)
            else:
                valid_items.append(f"({s})")

        if not valid_items:
            return ""

        if len(valid_items) == 1:
            return valid_items[0]

        op_str = f" {operator.value} "
        # 不再给整体再套一层括号
        return op_str.join(valid_items)


# -----------------------------------------------------------------------------
# 3. 筛选构造器 (Filter)
# -----------------------------------------------------------------------------

class FilterBuilder:
    """
    用于构建 filter 字符串
    格式: @@AND$$key$$val...
    """

    def __init__(self):
        self.filters = []

    def add_range(self, key: str, start: Any, end: Any):
        """
        添加数值/范围筛选
        示例: doc_if$$0$$3
        """
        self.filters.append(f"{key}$${start}$${end}")
        return self

    def add_value(self, key: str, value: Any):
        """
        添加单值筛选
        示例: doc_key$$value
        """
        self.filters.append(f"{key}$${value}")
        return self

    def add_options(self, key: str, values: List[Any]):
        """
        添加多选值筛选 (使用 $OR$ 连接)
        文档示例: doc_publish_type$$Clinical Study$OR$Clinical Trial
        """
        if not values:
            return self

        # 将列表转换为用 $OR$ 连接的字符串
        joined_values = "$OR$".join(str(v) for v in values)
        self.filters.append(f"{key}$${joined_values}")
        return self

    def add_publish_time(self, start_date: str, end_date: str):
        """
        添加发表时间筛选 (doc_publish_time)
        示例: 1957-01-01 到 2002-12-31
        """
        # 复用 add_range，key 固定为 doc_publish_time
        return self.add_range("doc_publish_time", start_date, end_date)

    def build(self) -> str:
        """生成最终的 filter 字符串"""
        if not self.filters:
            return ""
        # 必须以 @@AND 开头
        return "@@AND$$" + "@@AND$$".join(self.filters)


# -----------------------------------------------------------------------------
# 2. 校验逻辑 (新增部分)
# -----------------------------------------------------------------------------

def validate_search_params(query_string: str, filter_string: str="") -> str:
    """
    校验搜索参数格式。如果发现错误，返回具体的错误提示字符串；如果通过，返回 None。
    """
    # --- 1. Keywords (Query String) 校验 ---
    if not query_string or not query_string.strip():
        return "Error: query_string 不能为空。"

    # A. 括号平衡检查
    if query_string.count('(') != query_string.count(')'):
        return f"Error: query_string 中的括号不匹配 (左括号 {query_string.count('(')} 个, 右括号 {query_string.count(')')} 个)。请确保每个左括号都有对应的右括号。"

    valid_tags = {
        "Title", "Abstract", "Title/Abstract", "MeSH Terms",
        "Author", "Affiliation", "Journal", "First Author", "Last Author"
    }

    # 提取所有 [] 中的内容
    tags_in_query = re.findall(r'\[(.*?)\]', query_string)
    if not tags_in_query:
        return "缺少字段限定符，例如 [Title]"

    for tag in tags_in_query:
        if tag not in valid_tags:
            # 这是一个非常强的纠正信号：模型常把关键词放在括号里 [Lung Cancer]
            return f"检测到无效的字段限定符 '[{tag}]'。请注意：关键词不要放在方括号里！方括号里只能放字段名，如 'Lung Cancer'[Title]。"

    # B. 字段限定符检查 ([Title], [Abstract] 等)
    # 正则匹配 [...] 结构
    if not re.search(r'\[.*?\]', query_string):
        return "Error: 搜索词缺少字段限定符。严禁直接搜索单词，必须指定字段。例如: \"Lung Cancer\"[Title] 或 \"Immunotherapy\"[Abstract]。"

    if re.search(r'\]\s+["\(]', query_string):
        # 例子: [Title] "Immunotherapy" -> 缺 AND
        # 例子: [Title] ( -> 缺 AND
        if " AND " not in query_string and " OR " not in query_string and " NOT " not in query_string:
            return "多个搜索条件之间缺少逻辑运算符(AND/OR)。例如: (\"A\"[Title]) AND (\"B\"[Abstract])"

    # C. 逻辑连接符与括号包裹检查 (针对你的需求：每个搜索词应该用括号分割)
    # 检查是否存在 AND/OR/NOT 但周围没有括号的情况 (简单的启发式检查)
    # 如果包含逻辑运算符，建议整体结构清晰
    logic_ops = [' AND ', ' OR ', ' NOT ']
    has_logic = any(op in query_string for op in logic_ops)

    # 如果有逻辑运算，检查是否有括号。
    # 这是一个比较宽松的检查，只要有括号就行，避免过于严格误杀正确格式
    if has_logic and '(' not in query_string:
        return "Error: 使用逻辑运算符 (AND/OR/NOT) 时，建议使用括号明确优先级。例如: ((\"Lung Cancer\"[Title]) AND (\"Review\"[doc_publish_type]))。"

    # --- 2. Filter String 校验 ---
    if filter_string:
        # A. 前缀检查
        # if not filter_string.startswith("@@AND$$"):  # 经过验证其实不用@@AND$$开头也没问题
        #     return "Error: filter_string 格式错误。必须以 '@@AND$$' 开头。例如: @@AND$$doc_if$$5$$30"

        # B. 分隔符检查
        if "$$" not in filter_string:
            return "Error: filter_string 分隔符错误。请使用 '$$' 分隔键和值。"

        # C. 日期格式检查 (如果有时间筛选)
        if "doc_publish_time" in filter_string:
            # 简单的正则匹配 YYYY-MM-DD
            date_pattern = r"\d{4}-\d{2}-\d{2}"
            dates = re.findall(date_pattern, filter_string)
            if not dates:
                return "Error: doc_publish_time 日期格式错误。请使用 YYYY-MM-DD 格式。例如: 2023-01-01。"

    return None  # 校验通过


async def search_advanced(
        query_string: str,
        filter_string: str = "",
        sort_field: str = "relevant",
        page_num: int = 1,
        page_size: int = 5
) -> Dict[str, Any]:
    """
    """
    logger.info(f"MCP搜索请求: query_string='{query_string}', filter_string='{filter_string}'")

    result = {
    'code': 200,
    'msg': '成功',
    'records': [
        {
            'id': '8760',
            'title': '韩国全国肺癌队列6年数据分析：不同肺癌组织病理学类型的转移及治疗模式比较',
            'abstract': '背景：IV期肺癌的个体化管理需要更深入地理解不同组织学类型的转移模式以及局部治疗可能带来的获益。本研究旨在利用韩国全国肺癌数据库，识别不同肺癌组织学类型的胸内及胸外转移模式。\n方法：分析了2014年至2019年在韩国肺癌登记系统（KALC-R）中确诊的肺癌患者数据。纳入依据M分期判定为IV期的患者，以重点研究转移模式。\n结果：研究共纳入7,562例IV期肺癌患者，其中腺癌最为常见，占49.22%（3,722例）。M分期分布为：M1a占27.3%，M1b占56.3%，M1c占15.7%，未明确者占0.6%。腺鳞癌患者中出现三个及以上器官转移的比例最高（42.9%）。在所有组织学类型中，肝转移和骨转移均与生存率下降显著相关。在腺癌中，胸外转移部位之间存在显著相关性，尤其是骨与肝（比值比OR=3.93）以及肝与肾上腺（OR=2.85）。多因素分析显示，接受肺部病灶放疗的患者总体生存期（OS）显著改善（风险比HR=0.68；95%置信区间CI：0.60–0.78；P<0.001）。对胸外转移灶进行放疗同样显著提高生存率（HR=0.84；95% CI：0.77–0.93；P<0.001）。\n结论：深入理解不同肺癌组织学类型特异性的转移模式和治疗选择，对于优化治疗策略至关重要。',
            'authors': 'Jeong Uk Lim,Kyu Yean Kim,Ho Cheol Kim,Tae-Jung Kim,Hong Kwan Kim,Mi Hyoung Moon,Kyongmin Sarah Beck,Yang Gun Suh,Chang Hoon Song,Jin Seok Ahn,Jeong Eun Lee,Jae Hyun Jeon,Chi Young Jung,Jeong Su Cho,Yoo Duk Choi,Seung Sik Hwang,Young Sik Park,Soon Ho Yoon,Joon Young Choi,Chang-Min Choi,Seung Hun Jang,韩国肺癌协会,韩国中央癌症登记中心',
            'journal': 'Translational Lung Cancer Research（转化性肺癌研究）',
            'publish_date': '2025-02-28 00:00:00',
            'impact_factor': 3.5,
            'publication_type': '',
            'link': 'https://example.com/#/articleDetails?id=8760'
        },
        {
            'id': '2188',
            'title': '日本6644例切除的非小细胞肺癌预后研究：日本肺癌登记研究',
            'abstract': '为即将修订的肺癌TNM分期系统，有必要在大样本人群中评估现行1997版分期系统。2001年，日本肺癌登记联合委员会向320家日本医疗机构发放问卷，收集1994年接受原发性肺癌切除手术患者的预后及临床病理资料。最终从303家机构（94.7%）汇总了7,408例患者数据，其中6,644例非小细胞肺癌患者用于预后分析。总体5年生存率为52.6%。按临床分期（c期）划分的5年生存率分别为：IA期72.1%，IB期49.9%，IIA期48.7%，IIB期40.6%，IIIA期35.8%，IIIB期28.0%，IV期20.8%。除IB与IIA期、IIIB与IV期之间外，相邻分期之间的预后差异均具有统计学意义。按病理分期（p期）计算的5年生存率分别为：IA期79.5%，IB期60.1%，IIA期59.9%，IIB期42.2%，IIIA期29.8%，IIIB期19.3%，IV期20.0%。IB期与IIA期在临床和病理分期中的生存曲线几乎重叠，提示二者应合并为同一期别。总体而言，现行TNM分期系统能够较好地反映非小细胞肺癌的分期预后，未来修订应重点关注I期和II期的进一步细分。',
            'authors': 'Tomoyuki Goya,Hisao Asamura,Hirokuni Yoshimura,Harubumi Kato,Kaoru Shimokata,Ryosuke Tsuchiya,Yasunori Sohara,Toshimichi Miya,Etsuo Miyaoka,日本肺癌登记联合委员会',
            'journal': 'Lung Cancer（阿姆斯特丹）',
            'publish_date': '2005-11-01 00:00:00',
            'impact_factor': 4.4,
            'publication_type': '',
            'link': 'https://example.com/#/articleDetails?id=2188'
        },
        {
            'id': 2589,
            'title': '环境性石棉暴露与肺癌',
            'abstract': '除居住在石棉工业区、矿区或石棉污染住房附近外，在某些地区，由于天然土壤中“污染”有石棉纤维，也可发生环境性石棉暴露。本文综述了土耳其环境性石棉暴露与肺癌之间的关系。其他研究同样提示，环境性石棉暴露可增加肺癌风险。与环境性石棉暴露相关的肺癌患者通常在更年轻的年龄被诊断，且女性的风险与男性相当。我们的数据表明，暴露剂量与风险之间呈线性关系，无法确定安全阈值。因此，生活在高环境性石棉暴露风险地区的人群应被引导参与戒烟项目，并被视为肺癌筛查计划的潜在候选人。该领域仍亟需进一步研究。',
            'authors': 'Muzaffer Metintas,Guntulu Ak,Selma Metintas',
            'journal': 'Lung Cancer（阿姆斯特丹）',
            'publish_date': '2024-06-20 00:00:00',
            'impact_factor': 4.4,
            'publication_type': '综述',
            'link': 'https://example.com/#/articleDetails?id=2589'
        },
        {
            'id': '6548',
            'title': '小细胞肺癌及全部肺癌发病率趋势',
            'abstract': '背景：小细胞肺癌（SCLC）通常被认为约占全部肺癌的20%，但据报道其发生率随时间下降。本研究分析了英格兰东南部男性和女性中SCLC的发病率趋势，并与整体肺癌发病趋势进行比较。\n方法：纳入1970年至2007年间诊断的237,792例肺癌患者（ICD-10 C33–C34），采用泊松回归年龄-队列模型估计1890–1960出生队列的年龄别发病率，并使用欧洲标准人口计算年龄标准化发病率，同时按形态学分析不同肺癌亚型的趋势。\n结果：在最近时期，SCLC在男性和女性全部肺癌病例中分别占10%和11%；在已明确形态学类型的肺癌中，男性和女性中SCLC分别占15%和17%。SCLC的发病率在两性中均随时间和出生队列显著下降，且下降幅度大于全部肺癌。结论：SCLC发病率下降可能反映了吸烟率的降低以及香烟类型的变化。',
            'authors': 'Sharma P Riaz,Margreet Lüchtenborg,Victoria H Coupland,James Spicer,Michael D Peake,Henrik Møller',
            'journal': 'Lung Cancer（阿姆斯特丹）',
            'publish_date': '2012-03-01 00:00:00',
            'impact_factor': 4.4,
            'publication_type': '研究资助（非美国政府）',
            'link': 'https://example.com/#/articleDetails?id=6548'
        },
        {
            'id': 1848,
            'title': '肺癌相关T细胞受体谱作为I期肺癌早期检测的潜在生物标志物',
            'abstract': '背景：在无症状患者中实现肺癌的早期检测仍具挑战性，尤其是I期肺癌。鉴于肿瘤免疫原性的重要作用，我们假设肺癌相关T细胞受体（LC-aTCR）可作为I期肺癌早期检测的潜在生物标志物。\n方法：纳入接受低剂量CT（LDCT）筛查的人群，采集手术组织和外周血样本，进行基于DNA的T细胞受体（TCR）测序，并采用基于基序的算法解析特异性的肺癌相关TCR。\n结果：本研究共纳入146名参与真实世界LDCT筛查项目的个体，其中包括52例经病理证实的I期肺癌患者和94名非癌对照。在训练队列中定义了80种LC-aTCR。在验证队列中，对I期肺癌的检测显示出较高的敏感性（72%）和特异性（91%），ROC曲线下面积（AUC）为0.91（95% CI：0.85–0.96）。\n结论：本研究为利用血液TCR谱数据进行I期肺癌检测提供了新的思路，TCR检测与常规筛查相结合值得在更大规模人群中进一步验证。',
            'authors': 'Min Li,Chunliu Zhang,Shichao Deng,Li Li,Shiqing Liu,Jing Bai,Yaping Xu,Yanfang Guan,Xuefeng Xia,Lunquan Sun,David P Carbone,Chengping Hu',
            'journal': 'Lung Cancer（阿姆斯特丹）',
            'publish_date': '2021-12-16 00:00:00',
            'impact_factor': 4.4,
            'publication_type': '研究资助（非美国政府）',
            'link': 'https://example.com/#/articleDetails?id=1848'
        }
    ],
    'total': 375658
}
    logger.info(f"搜索完成: {result}")
    return result


if __name__ == "__main__":
    # 使用 SSE 模式启动，类似 wiki_retriver_mcp.py
    # 默认端口 8099 (可根据需要修改)
    asyncio.run(search_advanced(query_string="肺癌"))