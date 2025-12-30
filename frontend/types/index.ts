// 搜索工具响应格式
export interface SearchRecord {
  title: string;
  abstract: string;
  authors: string;
  journal: string;
  publish_date: string;
  impact_factor: number;
  publication_type: string;
  link: string;
}

export interface SearchToolResponse {
  code: number;
  msg: string;
  records: SearchRecord[];
}

export interface FunctionResponseData {
  type: 'function_response';
  id: string;
  name: string;
  response: SearchToolResponse;
}

export interface SearchResultPayload {
  query: string;
  records: SearchRecord[];
}

export interface TaskPayload {
  tool: 'translator' | 'ppt_generator';
  status: 'accepted' | 'running' | 'done' | 'failed';
  progress: number;
  message: string;
  result?: any;           // 任务结果数据
  result_url?: string;      // PPT下载链接等
  translation_text?: string; // 翻译结果文本
}

export type CardType = 'task' | 'search_result';

export interface JsonCard {
  type: CardType;
  version: string;
  id: string;
  payload: TaskPayload | SearchResultPayload;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  id: string;
  search_cards?: JsonCard[];    // 搜索结果卡片
  task_cards?: JsonCard[];      // 任务卡片
  function_call?: any; // 工具调用信息
  function_response?: any; // 工具响应信息
}

export interface ChatState {
  messages: Message[];
  isLoading: boolean;
}
