import asyncio
import json
import os
import dotenv
import time
from pydantic import BaseModel
import uuid
import sys
import httpx
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi import UploadFile, File, HTTPException, Form
from fastapi import FastAPI, HTTPException, Query, Request, Response
import logging

dotenv.load_dotenv()
logging.basicConfig(
    handlers=[
        logging.StreamHandler()
    ],
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    history: list = []
    search_result: list = []

# 搜索Agent
SEARCH_AGENT_URL = os.environ["SEARCH_AGENT_URL"]


async def call_search_agent(user_message: str, history: list = [], search_result=[],language: str = "chinese"):
    """调用 Search agent 获取流式响应（包含文本和工具调用信息）
    history: 历史聊天记录
    search_result： 最近的一次搜索结果
    """
    try:
        from a2a.client import A2AClient
        from a2a.types import MessageSendParams, SendStreamingMessageRequest

        timeout = httpx.Timeout(120.0)
        async with httpx.AsyncClient(timeout=timeout) as httpx_client:
            client = await A2AClient.get_client_from_agent_card_url(
                httpx_client, SEARCH_AGENT_URL
            )

            request_id = uuid.uuid4().hex

            send_message_payload = {
                'message': {
                    'role': 'user',
                    'parts': [{'type': 'text', 'text': user_message}],
                    'messageId': request_id,
                    'metadata': {
                        "language": language,
                        "history": history,
                        "search_result": search_result
                    }
                }
            }

            logger.info(f"[A2A] >>> Calling search agent: {user_message}")

            streaming_request = SendStreamingMessageRequest(
                id=request_id,
                params=MessageSendParams(**send_message_payload)
            )

            stream_response = client.send_message_streaming(streaming_request)

            chunk_count = 0
            async for chunk in stream_response:
                chunk_count += 1
                chunk_data = chunk.model_dump(mode='json', exclude_none=True)

                if chunk_data.get('result', {}).get('kind') == 'status-update':
                    status = chunk_data['result'].get('status', {})

                    if 'message' in status:
                        message = status['message']
                        if 'parts' in message:
                            for part in message['parts']:
                                part_kind = part.get('kind')

                                # 1. 处理文本
                                if part_kind == 'text' and 'text' in part:
                                    yield {"type": "text", "content": part['text']}
                                    logger.info(f"[A2A] <<< Streaming text chunk: {part['text'][:30]}...")

                                # 2. 处理工具
                                elif part_kind == 'data' and 'data' in part:
                                    inner_data_list = part['data'].get('data', [])
                                    for item in inner_data_list:
                                        item_type = item.get('type')
                                        if item_type == 'function_call':
                                            yield {"type": "function_call", "content": item}
                                            logger.info(f"[A2A] <<< Function Call: {item.get('name')}")
                                        elif item_type == 'function_response':
                                            yield {"type": "function_response", "content": item}
                                            logger.info(f"[A2A] <<< Function Response: {item.get('name')}")

                elif chunk_data.get('result', {}).get('kind') == 'artifact-update':
                    continue

    except ImportError:
        logger.error("[A2A] !!! a2a module not found")
        yield {"type": "error", "content": "系统配置错误：缺少必要的库。"}
    except Exception as e:
        logger.error(f"[A2A] !!! Error: {e}", exc_info=True)
        yield {"type": "error", "content": f"系统错误：{str(e)}"}


@app.post("/search/stream")
async def search_stream(request: ChatRequest):
    """搜索文献stream（SSE）
    
    Args:
        request.message: 用户消息
        request.history: 历史对话记录
        request.search_result: 最近一次的搜索结果（用于后续对话的上下文）
    """
    logger.info(f"[STREAM] Request: {request.message}")
    logger.info(f"[STREAM] Search result context: {len(request.search_result) if request.search_result else 0} items")
    # request.search_result是最近的一次搜索记录
    async def event_generator():
        try:
            chunk_sent = False
            async for chunk_obj in call_search_agent(request.message, request.history, request.search_result):
                if chunk_obj:
                    event_type = chunk_obj.get("type")
                    content = chunk_obj.get("content")

                    response_payload = {}

                    if event_type == "text":
                        response_payload = {"text": content}
                    elif event_type == "function_call":
                        response_payload = {"function_call": content}
                    elif event_type == "function_response":
                        response_payload = {"function_response": content}
                    elif event_type == "error":
                        response_payload = {"error": content}

                    if response_payload:
                        yield f"data: {json.dumps(response_payload, ensure_ascii=False)}\n\n"
                        chunk_sent = True

            if chunk_sent:
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'text': '抱歉，未能获取到回复。'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"[STREAM] Error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/ping")
def ping():
    return "Pong"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=10069)