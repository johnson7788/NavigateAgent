# 导航智能体的训练
## 1. 训练框架
agent-lightning结合verl进行GRPO强化学习训练, Agent框架使用openai-agents。

## 2. 环境准备

### Step1
```
同步post_train代码到服务器，
cd post_train
# 获取镜像
docker pull modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/modelscope:ubuntu22.04-cuda12.6.3-py311-torch2.7.1-vllm0.10.1.1-modelscope1.29.2-swift3.8.1

# 创建容器，如果只使用显卡1，不使用显卡0 --gpus "device=1"，如果公司的服务器，使用显卡1，并且swift更改名称，如果是云服务就不用更改这些命令
mkdir -p .cache
docker create \
  --runtime=nvidia --gpus all --net=host \
  --shm-size="10g" --cap-add=SYS_ADMIN \
  -v "$(pwd)":/workspace/post_train \
  -v "$HOME/.cache":/root/.cache \
  -v /etc/localtime:/etc/localtime:ro \
  -v /etc/timezone:/etc/timezone:ro \
  --name swift \
  modelscope-registry.cn-beijing.cr.aliyuncs.com/modelscope-repo/modelscope:ubuntu22.04-cuda12.6.3-py311-torch2.7.1-vllm0.10.1.1-modelscope1.29.2-swift3.8.1 \
  sleep infinity

# 启动容器
docker start swift
docker exec -it swift bash
```
### Step2: 进入容器开始安装agent-lightning
克隆agent-lightning
```
cd agent-lightning
pip install uv
uv pip install --system  --no-cache-dir -e .[dev,agent,apo] fastmcp==2.14.1 openai-agents==0.6.3 vllm==0.10.1.1 verl==0.5.0 'litellm[proxy]>=1.78' 'agentops>=0.4.21' 'openai>=2.0.0'
```

### Step3: 检查安装配置信息
python check_install.py

### Step4: 如果flash-attn报错
uv pip install --system torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 vllm

## 3. 训练步骤
```
# 1. 重启RAY： 配置Wandb环境变量和重启ray
export VERL_USE_MODELSCOPE=True
export WANDB_BASE_URL=http://xxxxx/
export WANDB_API_KEY=local-xxxxx
wandb login
bash restart_ray.sh

3. 启动Agent 
python rag_agent.py

4. 启动训练
bash train.sh
```


## 4. 文件
```
.
├── README.md
├── check_install.py
├── create_question.py
├── data
│   ├── README.md
│   ├── check_data_file.py
│   ├── seed_topic.txt
│   ├── train.parquet  #训练数据
│   └── val.parquet
├── env_template.txt
├── navi_agent.py   #训练的Agent
├── naviagent_test.py
├── tools.py  # 封装的pubmed搜索
└── train.sh   #遍历数据，调用Agent，然后根据Deepseek的结果+规则作为奖励进行GRPO训练
```

## 5.导航智能体的可用功能：
1. **内部数据库论文搜索工具**

   * 输入：用户的搜索问题/关键词
   * 输出：论文列表（包含标题、作者、摘要、链接等）

2. **论文翻译工具（长任务，只能对内部数据库进行处理）**

   * 输入：论文 id
   * 输出：任务已提交信息（任务 id、状态、查询入口等）
   * 任务完成后返回翻译结果引用

3. **论文生成 PPT 工具（长任务，只能对内部数据库进行处理）**

   * 输入：论文 id
   * 输出：任务已提交信息（任务 id、状态、查询入口等）
   * 任务完成后返回 PPT 文件/下载链接

### 6. 基本prompt
```
# 角色定义
你是一个专业的学术科研助手 "Navi Agent"。你的核心职责是作为系统的导航入口，准确理解用户的意图，并调用相应的工具来完成任务。

# 工具能力与调度逻辑

你需要根据用户的输入选择以下工具之一：

1. **内部医学数据库搜索 (search_document_db_tool)**
   - **触发场景**: 用户搜索论文、查找医学资料、或未指定来源的通用搜索。
   - **参数提取**: 提取用户查询的核心关键词 (keywords)。
   - **优先级**: 默认搜索工具。

2. **论文翻译 (translate_paper_tool)**
   - **触发场景**: 用户请求翻译某篇论文。
   - **参数提取**: 必须提供 `paper_id`。
   - **异常处理**: 如果用户未提供 paper_id（例如只说了"帮我翻译这篇"），请礼貌地询问用户先进行搜索，然后将根据搜索到的论文对某篇文章进行翻译。

3. **生成 PPT (generate_ppt_tool)**
   - **触发场景**: 用户请求为论文生成 PPT、演示文稿或幻灯片。
   - **参数提取**: 必须提供 `paper_id`。
   - **异常处理**: 如果用户未提供 paper_id，请礼貌地询问用户先进行搜索，然后将根据搜索到的论文对某篇文章生成PPT。

# 交互与输出规范

1. **工具优先**: 不要使用你自己的内部知识直接回答论文内容。遇到上述场景，**必须**调用工具。
2. **闲聊处理**: 如果用户只是打招呼（如 "你好"、"Hi"），请简短介绍你的四项能力（搜内网、搜Arxiv、翻译、生成PPT），并引导用户下达指令。
3. **拒绝无关任务**: 如果用户的问题完全超出了学术/科研/导航的范围（如"今天天气如何"），请礼貌拒绝并引导回科研任务。
注意：
- 工具调用会返回 JSONCARD，系统会自动保存并传给前端渲染。
- 你看到 JSONCARD 后，只需要用自然语言给用户做摘要说明，
  比如“我帮你找到 3 篇相关论文，分别讨论了 A / B / C”。
- 不要在回答里原样粘贴 JSONCARD，也不要输出其中的 paper_id。
- 当用户说“第二篇”“刚才那篇”时，你要根据最近的 JSONCARD 状态
  找到对应的论文，并在工具参数里填入正确的 paper_id，但不要对用户说出这个 id。


# 当前用户输入
{user_question}
```


### 7. 单条完整数据详细视图
id                      med_nav_5b17aca6
question    你好，能帮我查一下关于糖尿病并发症的最新系统综述文献吗？
answer                          动态回答（Deepseek判断回答)


### 8. 其它知识
```
# 模型数量:
Actor 模型（可训练）+ 优化器状态 + 梯度（AdamW 等）
Reference Policy（参考模型）GRPO 里为了算 KL，要同时跑 actor 和 ref。
推理进程里的模型（vLLM)，用于rollout和同步Actor的参数
（可选）Reward Model / RM --> 这里使用Deepseek代替


# 关于奖励
不需要在0-1之间，负数或者正数都是可以的
奖励需要更密集，更细致的奖励，即微小的进步也有奖励。例如写高级搜索表达式，写对了字段给分，写对了逻辑符给分，括号匹配给分。
奖励不要使用max(-6.0, min(6.0, reward))这样的裁剪，这样会不密集，需要使用缩放
如果奖励有不均匀，或者问题比较单一，模型就会陷入奖励高的解法，而缺乏探索能力，不进行更多尝试。

# 模型蒸馏的奖励
学生 Agent 接收医学问题后，按照规则生成搜索表达式并调用一次搜索工具获取真实结果。系统记录工具调用并根据规则合规性、是否检索到内容，以及 DeepSeek 教师对搜索质量的评分来计算奖励。教师模型还会基于当前对话生成新的医学问题，用于下一轮训练。重复多轮后累积奖励返回给 GRPO，用于更新学生模型，从而实现大模型在线蒸馏小模型的搜索能力。
```


