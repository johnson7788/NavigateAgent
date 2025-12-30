# PPT生成Agent

> 本项目提供PPT自动生成功能

## 简介

基于AI的PPT生成Agent，能够根据输入内容自动生成演示文稿。

## 文件说明

| 文件 | 说明 |
|------|------|
| `agent.py` | Agent主逻辑 |
| `tools.py` | 工具函数集合 |
| `main_api.py` | API接口服务 |
| `prompt.py` | 提示词模板 |
| `memory_controller.py` | 记忆控制器 |
| `create_model.py` | 模型创建工具 |
| `a2a_client.py` | A2A客户端 |
| `adk_agent_executor.py` | ADK执行器 |
| `cache_utils.py` | 缓存工具 |
| `requirements.txt` | 依赖包列表 |
| `.env` | 环境变量配置 |

## 环境配置

1. 复制 `env_template.txt` 为 `.env`
2. 配置必要的环境变量

## 依赖安装

```bash
pip install -r requirements.txt
```

## 运行服务

```bash
python main_api.py
```