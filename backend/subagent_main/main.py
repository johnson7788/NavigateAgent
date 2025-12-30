import asyncio
import json
import os
import re
import logging
import uuid
import threading
import time
import datetime
from typing import Dict, Optional, Any
from uuid import uuid4
import httpx
import dotenv
import pika
from pika.exceptions import AMQPConnectionError
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

# 导入本地翻译工具
from tools import translate_tool

dotenv.load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# import logging
# import os
# logger = logging.getLogger(__name__)
# logger.setLevel(logging.INFO)
# file_handler = logging.FileHandler(
#     os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.log"),
#     encoding="utf-8")
# file_handler.setLevel(logging.INFO)
# file_handler.setFormatter(logging.Formatter(
#     "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S"
# ))
# logger.addHandler(file_handler)

app = FastAPI(title="Sub Agent API tool", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# RabbitMQ Configuration
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USERNAME = os.getenv("RABBITMQ_USERNAME", "admin")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "welcome")
RABBITMQ_VIRTUAL_HOST = os.getenv("RABBITMQ_VIRTUAL_HOST", "/")
QUEUE_NAME_WRITER = os.getenv("QUEUE_NAME_WRITER", "question_queue")
QUEUE_NAME_READ = os.getenv("QUEUE_NAME_READ", "answer_queue")

logger.info(f"连接 RabbitMQ at {RABBITMQ_HOST}:{RABBITMQ_PORT}, user: {RABBITMQ_USERNAME}")

# 缓存所有Agent的任务结果：task_id -> result
task_results: Dict[str, Any] = {}

# WebSocket连接管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.active_connections[task_id] = websocket
        logger.info(f"WebSocket连接建立，task_id: {task_id}")

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]
            logger.info(f"WebSocket连接断开，task_id: {task_id}")

    async def send_personal_message(self, message: str, task_id: str):
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_text(message)
            except Exception as e:
                logger.error(f"发送消息给task_id {task_id}失败: {e}")
                self.disconnect(task_id)

manager = ConnectionManager()

# 全局 event loop 引用，用于从后台线程安全地调度异步任务
main_loop: asyncio.AbstractEventLoop = None

# Agent URLs
TRANSLATOR_AGENT_URL = os.getenv("TRANSLATOR_AGENT_URL")
PPT_AGENT_URL = os.getenv("PPT_AGENT_URL")

AGENT_URLS = {
    "translator": TRANSLATOR_AGENT_URL,
    "ppt_generator": PPT_AGENT_URL
}

# ===================== RabbitMQ 连接 =====================
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


def process_tool_request(tool_request: Dict[str, Any]):
    """
    处理工具请求，调用对应的Agent或本地工具
    """
    try:
        tool_name = tool_request.get("tool", {}).get("name")
        task_id = tool_request.get("task_id")
        args = tool_request.get("tool", {}).get("args", {})
        
        logger.info(f"处理工具请求: {tool_name}, task_id: {task_id}")
        
        # 翻译工具使用本地函数处理（直接查询 MongoDB）
        if tool_name == "translator":
            if main_loop and main_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    call_translate_tool_async(task_id, args),
                    main_loop
                )
            else:
                logger.error(f"主 event loop 未运行，无法执行翻译任务")
                error_result = {
                    "type": "error",
                    "version": "1.0", 
                    "id": f"error_{uuid.uuid4().hex}",
                    "payload": {"message": "服务未完全启动，无法处理翻译任务"}
                }
                task_results[task_id] = error_result
            return
        
        # 其他工具使用远程 Agent 处理
        if tool_name not in AGENT_URLS:
            error_result = {
                "type": "error",
                "version": "1.0", 
                "id": f"error_{uuid.uuid4().hex}",
                "payload": {"message": f"未知的工具类型: {tool_name}"}
            }
            task_results[task_id] = error_result
            return
        
        # 从后台线程安全地调度异步任务到主 event loop
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                call_agent_async(tool_name, task_id, args),
                main_loop
            )
        else:
            logger.error(f"主 event loop 未运行，无法执行异步任务: {tool_name}")
            error_result = {
                "type": "error",
                "version": "1.0", 
                "id": f"error_{uuid.uuid4().hex}",
                "payload": {"message": "服务未完全启动，无法处理任务"}
            }
            task_results[task_id] = error_result
        
    except Exception as e:
        logger.error(f"处理工具请求失败: {e}")
        error_result = {
            "type": "error",
            "version": "1.0",
            "id": f"error_{uuid.uuid4().hex}", 
            "payload": {"message": f"处理请求失败: {str(e)}"}
        }
        task_results[task_id] = error_result


async def call_translate_tool_async(task_id: str, args: Dict[str, Any]):
    """
    本地调用翻译工具，直接从 MongoDB 查询论文的中文翻译内容
    """
    try:
        paper_id = int(args.get('paper_id'))
        if not paper_id:
            raise ValueError("缺少必要参数: paper_id")
        
        logger.info(f"调用本地翻译工具，paper_id: {paper_id}")
        
        # 调用本地翻译工具查询 MongoDB
        translation_text =await translate_tool(doc_id=paper_id)
        logger.info(f"❤️❤️❤️❤️{paper_id}:{translation_text}")
        
        # 构造结果（与 build_ws_message 中的 translation_result 类型对应）
        result = [{
            "type": "translation_result",
            "id": f"translation_{uuid.uuid4().hex}",
            "text": translation_text,
            "paper_id": paper_id,
        }]
        
        task_results[task_id] = result
        logger.info(f"翻译工具执行成功，paper_id: {paper_id}, 结果长度: {len(translation_text)}")
        
    except Exception as e:
        logger.error(f"翻译工具执行失败: {e}")
        error_result = {
            "type": "error",
            "version": "1.0",
            "id": f"error_{uuid.uuid4().hex}",
            "payload": {"message": f"翻译失败: {str(e)}"}
        }
        task_results[task_id] = error_result
    
    finally:
        # 如果有 WebSocket 连接，通知结果已准备好
        if task_id in manager.active_connections:
            try:
                result_data = task_results.get(task_id)
                ws_message = build_ws_message(task_id, result_data)
                logger.info(f"发送翻译结果 WebSocket 消息: {ws_message}")
                await manager.send_personal_message(json.dumps(ws_message), task_id)
            except Exception as e:
                logger.error(f"通知 WebSocket 翻译结果失败: {e}")


def build_ws_message(task_id: str, result_data: Any) -> Dict[str, Any]:
    """
    根据任务结果构建 WebSocket 消息
    支持 PPT 结果、翻译结果、错误等不同类型
    """
    ws_message = {
        "task_id": task_id,
        "status": "done",
        "result": result_data,
        "message": "任务完成"
    }
    
    # 根据不同的结果类型，设置不同的字段
    if isinstance(result_data, list):
        for item in result_data:
            item_type = item.get('type')
            
            # 错误结果
            if item_type == 'error':
                ws_message["status"] = "failed"
                error_msg = item.get('payload', {}).get('message', '未知错误')
                ws_message["message"] = f"任务失败: {error_msg}"
                ws_message["error"] = error_msg
                break
            
            # PPT 结果：包含下载 URL
            elif item_type == 'ppt_result' and item.get('url'):
                ws_message["result_url"] = item.get('url')
                ws_message["message"] = "PPT生成完成，点击查看"
                break
            
            # 翻译结果：包含翻译后的文本
            elif item_type == 'translation_result':
                ws_message["translation_text"] = item.get('text', '')
                ws_message["message"] = "翻译完成"
                if item.get('url'):
                    ws_message["result_url"] = item.get('url')
                break
                
    elif isinstance(result_data, dict):
        item_type = result_data.get('type')
        
        # 错误结果
        if item_type == 'error':
            ws_message["status"] = "failed"
            error_msg = result_data.get('payload', {}).get('message', '未知错误')
            ws_message["message"] = f"任务失败: {error_msg}"
            ws_message["error"] = error_msg
        
        elif item_type == 'ppt_result' and result_data.get('url'):
            ws_message["result_url"] = result_data.get('url')
            ws_message["message"] = "PPT生成完成，点击查看"
        
        elif item_type == 'translation_result':
            ws_message["translation_text"] = result_data.get('text', '')
            ws_message["message"] = "翻译完成"
            if result_data.get('url'):
                ws_message["result_url"] = result_data.get('url')
    
    return ws_message


async def call_agent_async(tool_name: str, task_id: str, args: Dict[str, Any]):
    """
    异步调用Agent
    """
    try:
        agent_url = AGENT_URLS[tool_name]
        if not agent_url:
            raise ValueError(f"未配置 {tool_name} Agent的URL")
            
        # 构造调用消息
        if tool_name == "translator":
            user_message = f"请翻译论文，论文ID: {args.get('paper_id')}, 目标语言: {args.get('target_lang', 'zh-CN')}"
        elif tool_name == "ppt_generator":
            user_message = f"请为论文生成PPT，论文ID: {args.get('paper_id')}"
        else:
            user_message = f"执行工具: {tool_name}, 参数: {args}"
            
        logger.info(f"调用Agent: {tool_name}, URL: {agent_url}")
        
        # 调用Agent
        result_chunks = []
        async for chunk in call_agent(agent_url, user_message):
            result_chunks.append(chunk)
            
        # 组合完整结果
        full_result = "".join(result_chunks)
        
        # 尝试解析JSONCARD
        try:
            # 提取JSONCARD内容
            jsoncard_match = re.search(r'```JSONCARD\s*\n(.*?)\n```', full_result, re.DOTALL)
            if jsoncard_match:
                jsoncard_content = jsoncard_match.group(1)
                parsed_result = json.loads(jsoncard_content)
                task_results[task_id] = parsed_result
                logger.info(f"Agent {tool_name} 执行成功，已缓存结果: {str(parsed_result)[:200]}...")
            else:
                # 如果没有JSONCARD格式，包装成error
                error_result = {
                    "type": "error",
                    "version": "1.0",
                    "id": f"error_{uuid.uuid4().hex}",
                    "payload": {"message": f"Agent返回格式错误: {full_result[:200]}..."}
                }
                task_results[task_id] = error_result
        except json.JSONDecodeError as e:
            error_result = {
                "type": "error", 
                "version": "1.0",
                "id": f"error_{uuid.uuid4().hex}",
                "payload": {"message": f"解析Agent返回结果失败: {str(e)}"}
            }
            task_results[task_id] = error_result
            
    except Exception as e:
        logger.error(f"调用Agent {tool_name} 失败: {e}")
        error_result = {
            "type": "error",
            "version": "1.0", 
            "id": f"error_{uuid.uuid4().hex}",
            "payload": {"message": f"Agent调用失败: {str(e)}"}
        }
        task_results[task_id] = error_result
    
    finally:
        # 如果有WebSocket连接，通知结果已准备好
        if task_id in manager.active_connections:
            try:
                result_data = task_results.get(task_id)
                ws_message = build_ws_message(task_id, result_data)
                
                logger.info(f"发送WebSocket消息: {ws_message}")
                await manager.send_personal_message(json.dumps(ws_message), task_id)
            except Exception as e:
                logger.error(f"通知WebSocket结果失败: {e}")


def listen_to_question_queue():
    """
    后台线程：持续监听 MQ 的工具请求
    收到消息后，调用对应的Agent处理
    """
    while True:
        try:
            connection = get_rabbitmq_connection()
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME_WRITER, durable=True)

            logger.info(f"开始监听 RabbitMQ 队列： {QUEUE_NAME_WRITER}")

            for method_frame, properties, body in channel.consume(QUEUE_NAME_WRITER):
                try:
                    message = json.loads(body.decode('utf-8'))
                    
                    # 检查是否是工具请求
                    if message.get("type") == "tool_request":
                        process_tool_request(message)
                    
                    # 确认消费
                    channel.basic_ack(method_frame.delivery_tag)
                    
                except Exception as e:
                    logger.error(f"处理 MQ 消息时发生错误: {e}")
                    # 避免毒消息反复重试，不重新入队
                    channel.basic_nack(method_frame.delivery_tag, requeue=False)

        except (AMQPConnectionError, pika.exceptions.StreamLostError) as e:
            logger.error(f"RabbitMQ 连接错误: {e}. 5秒后尝试重连...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"RabbitMQ 监听线程发生未知异常: {e}")
            time.sleep(10)



async def call_agent(agent_url, user_message: str, history: list = [], language: str = "chinese"):
    """调用 agent 获取流式响应"""
    try:
        from a2a.client import A2AClient
        from a2a.types import MessageSendParams, SendStreamingMessageRequest

        timeout = httpx.Timeout(120.0)
        async with httpx.AsyncClient(timeout=timeout) as httpx_client:
            client = await A2AClient.get_client_from_agent_card_url(
                httpx_client, agent_url
            )

            request_id = uuid.uuid4().hex

            # 准备当前用户消息
            send_message_payload = {
                'message': {
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': user_message}],
                    'messageId': request_id,
                    'metadata': {
                        "language": language,
                        "history_count": len(history)
                    }
                }
            }

            # 将历史对话信息添加到metadata中
            if history:
                history_text = "\n\n历史对话:\n"
                for i, history_msg in enumerate(history):
                    role = "用户" if history_msg.get('role') == 'user' else "助手"
                    history_text += f"{i + 1}. {role}: {history_msg.get('content', '')}\n"

                send_message_payload['message']['parts'][0]['text'] += history_text
                logger.info(f"[A2A] 包含 {len(history)} 条历史对话记录")

            logger.info(f"[A2A] >>> Calling agent: {user_message}")

            streaming_request = SendStreamingMessageRequest(
                id=request_id,
                params=MessageSendParams(**send_message_payload)
            )

            stream_response = client.send_message_streaming(streaming_request)

            chunk_count = 0
            async for chunk in stream_response:
                chunk_count += 1
                chunk_data = chunk.model_dump(mode='json', exclude_none=True)
                logger.info(chunk_data)

                # 只处理 status-update 中的 message
                if chunk_data.get('result', {}).get('kind') == 'status-update':
                    status = chunk_data['result'].get('status', {})

                    # 检查是否有 message 字段（包含流式文本片段）
                    if 'message' in status:
                        message = status['message']
                        if 'parts' in message:
                            for part in message['parts']:
                                if part.get('kind') == 'text' and 'text' in part:
                                    yield part['text']
                                    logger.info(f"[A2A] <<< Streaming chunk {chunk_count}: {part['text'][:50]}...")

                # 处理 artifact-update（包含完整的最终结果文本，包括 JSONCARD）
                elif chunk_data.get('result', {}).get('kind') == 'artifact-update':
                    artifact = chunk_data['result'].get('artifact', {})
                    parts = artifact.get('parts', [])
                    for part in parts:
                        if part.get('kind') == 'text' and 'text' in part:
                            text = part['text']
                            logger.info(f"[A2A] <<< Artifact text received, length: {len(text)}")
                            yield text

    except ImportError:
        logger.error("[A2A] !!! a2a module not found")
        yield "系统配置错误：缺少必要的库。"
    except Exception as e:
        logger.error(f"[A2A] !!! Error: {e}", exc_info=True)
        yield f"系统错误：{str(e)}"


@app.on_event("startup")
async def startup_event():
    """启动时初始化 event loop 引用并开启 RabbitMQ 监听线程"""
    global main_loop
    main_loop = asyncio.get_running_loop()
    logger.info(f"主 event loop 已初始化: {main_loop}")
    listener_thread = threading.Thread(target=listen_to_question_queue, daemon=True)
    listener_thread.start()

# ===================== WebSocket 接口 =====================

@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket 主入口。
    前端通过task_id连接，获取任务状态和结果
    """
    await manager.connect(websocket, task_id)
    
    try:
        logger.info(f"WebSocket连接建立，task_id: {task_id}")
        
        # 如果任务已完成，立即发送结果并退出
        if task_id in task_results:
            result = task_results[task_id]
            logger.info(f"任务已完成，立即发送结果: task_id={task_id}")
            
            ws_message = build_ws_message(task_id, result)
            await websocket.send_json(ws_message)
            return  # 发送后直接退出
        
        # 保持连接直到任务完成或连接断开
        while task_id in manager.active_connections:
            try:
                # 等待消息或超时
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                
                # 处理前端消息（可选）
                if data == "ping":
                    await websocket.send_text("pong")
                    
            except asyncio.TimeoutError:
                # 检查任务是否完成
                if task_id in task_results:
                    result = task_results[task_id]
                    ws_message = build_ws_message(task_id, result)
                    await websocket.send_json(ws_message)
                    break
                continue
            except Exception as e:
                logger.error(f"WebSocket接收消息错误: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket连接断开，task_id: {task_id}")
    except Exception as e:
        logger.error(f"WebSocket发生异常: {e}")
    finally:
        manager.disconnect(task_id)


@app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """
    HTTP接口：获取任务状态和结果
    """
    if task_id in task_results:
        return {
            "task_id": task_id,
            "status": "done",
            "result": task_results[task_id]
        }
    else:
        return {
            "task_id": task_id,
            "status": "running",
            "message": "任务正在处理中..."
        }


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "active_tasks": len(task_results)
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=10072)