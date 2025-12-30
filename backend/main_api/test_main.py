#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Date  : 2025/12/23 20:18
# @File  : test_main.py
# @Author: johnson
# @Contact : github: johnson7788
# @Desc  :

import os
import time
import json
import unittest
import httpx
from httpx import AsyncClient

def truncate_value(value, max_len=100):
    """截断过长的字符串/列表/字典的打印"""
    if isinstance(value, str):
        return value if len(value) <= max_len else value[:max_len] + "...(截断)"
    elif isinstance(value, (list, tuple)):
        # 如果长度很长，只使用前4个
        if len(value) > 4:
            value = value[:4]
        return [truncate_value(v, max_len) for v in value]
    elif isinstance(value, dict):
        return {k: truncate_value(v, max_len) for k, v in value.items()}
    else:
        return value

def pretty_print_sse_data(data_dict):
    """根据SSE数据类型进行格式化打印"""
    if not isinstance(data_dict, dict):
        print(f"  数据格式错误: {data_dict}")
        return
    
    # 根据数据类型进行不同的打印格式
    if "text" in data_dict:
        text_content = data_dict["text"]
        print(f"  📝 文本内容:")
        print(f"     {truncate_value(text_content, 200)}")
        
    elif "function_call" in data_dict:
        func_call = data_dict["function_call"]
        print(f"  🔧 函数调用:")
        print(f"     函数名: {func_call.get('name', 'N/A')}")
        if 'arguments' in func_call:
            print(f"     参数: {truncate_value(func_call['arguments'], 150)}")
            
    elif "function_response" in data_dict:
        func_response = data_dict["function_response"]
        print(f"  📋 函数响应:")
        print(f"     函数名: {func_response.get('name', 'N/A')}")
        if 'content' in func_response:
            print(f"     内容: {truncate_value(func_response['content'], 150)}")
            
    elif "error" in data_dict:
        error_msg = data_dict["error"]
        print(f"  ❌ 错误信息:")
        print(f"     {error_msg}")
        
    elif "done" in data_dict:
        print(f"  ✅ 流结束")
        
    else:
        # 其他未知格式
        print(f"  📄 其他数据:")
        print(f"     {json.dumps(truncate_value(data_dict, 200), ensure_ascii=False, indent=2)}")

def parse_sse_stream(response):
    """解析SSE流，返回事件列表"""
    events = []
    buffer = ""
    
    for chunk in response.iter_text():
        if not chunk:
            continue
            
        buffer += chunk
        
        # 处理事件分隔符 \n\n
        while "\n\n" in buffer:
            event_text, buffer = buffer.split("\n\n", 1)
            
            # 解析事件数据
            data_lines = []
            for line in event_text.split("\n"):
                if line.startswith("data:"):
                    data_lines.append(line[5:].strip())  # 移除 "data: " 前缀
            
            if data_lines:
                data_str = "\n".join(data_lines)
                try:
                    data_dict = json.loads(data_str)
                    events.append(data_dict)
                except json.JSONDecodeError:
                    print(f"⚠️  JSON解析失败: {data_str}")
                    
    return events

class NaviApiTestCase(unittest.IsolatedAsyncioTestCase):
    """
    测试：搜索接口
    - POST /search/stream
    运行前请确保 main_api.py 已启动（默认 http://127.0.0.1:10069）
    可以通过环境变量覆盖：
      host=http://127.0.0.1  port=10069
    """
    host = os.environ.get('host', 'http://127.0.0.1')
    port = os.environ.get('port', 10069)
    base_url = f"{host}:{port}"

    def test_search_stream(self):
        """测试搜索流式接口"""
        print(f"\n🚀 开始测试搜索流式接口...")
        print(f"📍 服务器地址: {self.base_url}")
        
        url = f"{self.base_url}/search/stream"
        req = {
            "message": "搜索一篇肺癌的文献",
        }
        
        print(f"📤 发送请求: {json.dumps(req, ensure_ascii=False)}")
        start_time = time.time()
        
        try:
            with httpx.stream("POST", url, json=req, timeout=120.0) as response:
                # 验证响应头
                content_type = response.headers.get("content-type", "")
                print(f"📥 响应类型: {content_type}")
                
                if not content_type.startswith("text/event-stream"):
                    print(f"⚠️  警告: 期望text/event-stream，实际得到: {content_type}")
                
                # 解析SSE流
                events = parse_sse_stream(response)
                
                print(f"\n📊 收到 {len(events)} 个事件:")
                print("=" * 60)
                
                for i, event_data in enumerate(events, 1):
                    print(f"\n🔸 事件 #{i}:")
                    pretty_print_sse_data(event_data)
                    
                print("\n" + "=" * 60)
                elapsed_time = time.time() - start_time
                print(f"⏱️  测试完成，耗时: {elapsed_time:.2f}秒")
                
                # 统计不同类型的事件
                event_types = {}
                for event in events:
                    for key in event.keys():
                        event_types[key] = event_types.get(key, 0) + 1
                
                print(f"📈 事件统计: {event_types}")
                
        except httpx.TimeoutException:
            print("❌ 请求超时")
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            raise

    def test_chat_stream(self):
        """测试聊天流式接口"""
        print(f"\n🚀 开始测试聊天流式接口...")
        print(f"📍 服务器地址: {self.base_url}")
        
        url = f"{self.base_url}/chat/stream"
        req = {
            "message": "你好，请介绍一下人工智能",
            "history": []
        }
        
        print(f"📤 发送请求: {json.dumps(req, ensure_ascii=False)}")
        start_time = time.time()
        
        try:
            with httpx.stream("POST", url, json=req, timeout=120.0) as response:
                # 验证响应头
                content_type = response.headers.get("content-type", "")
                print(f"📥 响应类型: {content_type}")
                
                # 解析SSE流
                events = parse_sse_stream(response)
                
                print(f"\n📊 收到 {len(events)} 个事件:")
                print("=" * 60)
                
                for i, event_data in enumerate(events, 1):
                    print(f"\n🔸 事件 #{i}:")
                    pretty_print_sse_data(event_data)
                    
                print("\n" + "=" * 60)
                elapsed_time = time.time() - start_time
                print(f"⏱️  测试完成，耗时: {elapsed_time:.2f}秒")
                
        except httpx.TimeoutException:
            print("❌ 请求超时")
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            raise


if __name__ == "__main__":
    unittest.main(verbosity=2)

