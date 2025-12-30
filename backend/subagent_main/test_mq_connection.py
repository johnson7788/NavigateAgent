#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试MQ连接的简单脚本
"""

import json
import os
import pika
import dotenv

dotenv.load_dotenv()

# RabbitMQ配置
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBITMQ_USERNAME = os.getenv("RABBITMQ_USERNAME", "admin")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "welcome")
RABBITMQ_VIRTUAL_HOST = os.getenv("RABBITMQ_VIRTUAL_HOST", "/")
QUEUE_NAME_WRITER = os.getenv("QUEUE_NAME_WRITER", "question_queue")

def test_rabbitmq_connection():
    """测试RabbitMQ连接"""
    try:
        # 创建连接
        credentials = pika.PlainCredentials(RABBITMQ_USERNAME, RABBITMQ_PASSWORD)
        parameters = pika.ConnectionParameters(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            virtual_host=RABBITMQ_VIRTUAL_HOST,
            credentials=credentials,
            heartbeat=600
        )
        
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # 声明队列
        channel.queue_declare(queue=QUEUE_NAME_WRITER, durable=True)
        
        print(f"✅ RabbitMQ连接成功")
        print(f"   Host: {RABBITMQ_HOST}:{RABBITMQ_PORT}")
        print(f"   Virtual Host: {RABBITMQ_VIRTUAL_HOST}")
        print(f"   Queue: {QUEUE_NAME_WRITER}")
        
        # 发送测试消息
        test_message = {
            "type": "tool_request",
            "version": "1.0",
            "task_id": "test_task_123",
            "trace_id": "test_trace_456",
            "timestamp": "2025-12-11T10:00:00+08:00",
            "tool": {
                "name": "translator",
                "args": {
                    "paper_id": "test_paper_123",
                    "target_lang": "zh-CN"
                }
            }
        }
        
        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME_WRITER,
            body=json.dumps(test_message, ensure_ascii=False),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        
        print(f"✅ 测试消息已发送到队列 {QUEUE_NAME_WRITER}")
        print(f"   消息内容: {json.dumps(test_message, ensure_ascii=False, indent=2)}")
        
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ RabbitMQ连接失败: {e}")
        return False

if __name__ == "__main__":
    print("开始测试MQ连接...")
    success = test_rabbitmq_connection()
    if success:
        print("\n🎉 MQ连接测试通过！")
    else:
        print("\n💥 MQ连接测试失败！")