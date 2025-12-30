# 安装和启动
## 拷贝环境变量
```cp env_template .env```

## 安装和启动
```
npm install
npm run dev
```

## 导航接口
http://localhost:3030/

## 文献搜索接口
http://localhost:3030/search


# 文件
```
app
├── api  # 请求的api路由
│   ├── chat
│   │   └── stream
│   │       └── route.ts
│   ├── check
│   │   └── route.ts
│   └── search
│       └── stream
│           └── route.ts
├── globals.css
├── layout.tsx 
├── page.tsx  /* 根页面，主搜索示例 */
└── search
    └── page.tsx   /search搜索示例，使用tool的结果作为传输
components
├── ChatInterface.tsx
├── MessageBubble.tsx
├── SearchInterface.tsx
├── cards
│   ├── PaperCard.tsx。  /主页面使用的论文显示的卡片
│   ├── SearchResultCard.tsx   /search页面使用的论文卡片
│   └── TaskCard.tsx  //任务状态卡片
```

MessageBubble中显示不同的card类型
```
  case 'paper_result':
        return <PaperCard key={`${card.id}-${index}`} data={card.payload as PaperResultPayload} />;
      case 'task':
        return <TaskCard key={`${card.id}-${index}`} id={card.id} initialData={card.payload as TaskPayload} />;
      case 'search_result':
        return <SearchResultCard key={`${card.id}-${index}`} records={(card.payload as SearchResultPayload).records} query={(card.payload as SearchResultPayload).query} />;
      
```