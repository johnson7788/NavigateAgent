import React, { useState, useRef, useEffect } from 'react';
import { Search, StopCircle } from 'lucide-react';
import { MessageBubble } from './MessageBubble';
import { Message } from '../types';
import { parseContentWithCards } from '../lib/utils';

export const SearchInterface: React.FC = () => {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchResult, setSearchResult] = useState<any[]>([]); // 维护最近的搜索结果
  const [isDebugMode, setIsDebugMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('debugMode');
      return saved ? JSON.parse(saved) : false;
    }
    return false;
  });
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const toggleDebugMode = () => {
    const newValue = !isDebugMode;
    setIsDebugMode(newValue);
    localStorage.setItem('debugMode', JSON.stringify(newValue));
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      role: 'user',
      content: input,
      id: Date.now().toString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    const assistantId = (Date.now() + 1).toString();
    // Initialize empty assistant message
    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', id: assistantId, search_cards: [], task_cards: [] }
    ]);

    try {
      // 准备历史对话（不包括当前用户消息和空的助手消息）
      const historyMessages = messages
        .filter(msg => msg.content.trim().length > 0) // 过滤空消息
        .map(msg => ({
          role: msg.role,
          content: msg.content
        }));

      const response = await fetch('/api/search/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: userMessage.content,
          history: historyMessages,
          search_result: searchResult
        }),
      });

      if (!response.ok) throw new Error('Network response was not ok');
      if (!response.body) throw new Error('No body in response');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullText = '';
      let functionCalls: any[] = [];
      let functionResponses: any[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        // The backend sends SSE formatted like "data: { ... }"
        // We need to parse these lines.
        const lines = chunk.split('\n\n');
        
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const jsonStr = line.slice(6);
                if (jsonStr === '[DONE]') continue; // Standard SSE done
                try {
                    const data = JSON.parse(jsonStr);
                    
                    if (data.done) {
                        // End of stream logic if explicitly sent
                    } else if (data.text) {
                        fullText += data.text;

                        // 检查是否是搜索工具调用过的消息
                        const hasSearchCall = functionCalls.some(call =>
                            call.name && call.name.startsWith('search_')
                        );

                        if (hasSearchCall) {
                            // 如果有搜索工具调用，只显示文本内容，不解析JSONCARD
                            setMessages((prev) =>
                                prev.map((msg) =>
                                    msg.id === assistantId
                                    ? { ...msg, content: fullText }
                                    : msg
                                )
                            );
                        } else {
                            // 没有搜索工具调用时，继续解析JSONCARD
                            const { cleanText, cards } = parseContentWithCards(fullText);
                            // 根据卡片类型分别处理
                            const searchCards: any[] = [];
                            const taskCards: any[] = [];
                            cards.forEach((card: any) => {
                                if (card.type === 'task') {
                                    taskCards.push(card);
                                } else if (card.type === 'search_result') {
                                    searchCards.push(card);
                                }
                            });

                            setMessages((prev) =>
                                prev.map((msg) =>
                                    msg.id === assistantId
                                    ? { 
                                        ...msg, 
                                        content: cleanText, 
                                        // 分别更新两种卡片类型
                                        search_cards: searchCards.length > 0 ? searchCards : (msg.search_cards || []),
                                        task_cards: taskCards.length > 0 ? taskCards : (msg.task_cards || [])
                                    }
                                    : msg
                                )
                            );
                        }
                    } else if (data.function_call) {
                        functionCalls.push(data.function_call);
                        setMessages((prev) => 
                            prev.map((msg) => 
                                msg.id === assistantId 
                                ? { ...msg, function_call: data.function_call } 
                                : msg
                            )
                        );
                    } else if (data.function_response) {
                        functionResponses.push(data.function_response);

                        // 如果是搜索工具响应，直接提取搜索结果并转换为卡片
                        let searchCards: any[] = [];
                        let taskCards: any[] = [];

                        if (data.function_response.name && data.function_response.name.startsWith('search_')) {
                            const searchResponse = data.function_response.response;
                            if (searchResponse && searchResponse.records) {
                                // 查找对应的搜索查询
                                const searchCall = functionCalls.find(call => call.name === data.function_response.name);
                                const query = searchCall?.args?.query_string || searchCall?.arguments?.query_string || '';

                                // 创建搜索结果卡片
                                searchCards = [{
                                    type: 'search_result',
                                    version: '1.0',
                                    id: `search_${Date.now()}`,
                                    payload: {
                                        query: query,
                                        records: searchResponse.records
                                    }
                                }];

                                // 更新 searchResult 状态，保存最近的搜索记录
                                setSearchResult(searchResponse.records);
                            }
                        }
                        // 如果是 translate_paper_tool 或 generate_ppt_tool，解析 JSONCARD
                        else if (data.function_response.name === 'translate_paper_tool' || data.function_response.name === 'generate_ppt_tool') {
                            const response = data.function_response.response;
                            if (response && response.result) {
                                // 解析 JSONCARD
                                try {
                                    const jsonCardStr = response.result;
                                    // 提取 JSONCARD 内容（去掉 ```JSONCARD 和 ```）
                                    const jsonMatch = jsonCardStr.match(/```JSONCARD\n([\s\S]*?)\n```/);
                                    if (jsonMatch && jsonMatch[1]) {
                                        const parsedCards = JSON.parse(jsonMatch[1]);
                                        // 根据卡片类型分别添加到对应的数组
                                        parsedCards.forEach((card: any) => {
                                            if (card.type === 'task') {
                                                taskCards.push(card);
                                            } else if (card.type === 'search_result') {
                                                searchCards.push(card);
                                            }
                                        });
                                    }
                                } catch (e) {
                                    console.warn('Failed to parse JSONCARD:', e);
                                }
                            }
                        }

                        setMessages((prev) =>
                            prev.map((msg) =>
                                msg.id === assistantId
                                ? {
                                    ...msg,
                                    function_response: data.function_response,
                                    // 分别更新 search_cards 和 task_cards
                                    search_cards: searchCards.length > 0 ? searchCards : (msg as Message).search_cards || [],
                                    task_cards: taskCards.length > 0 ? [...(msg.task_cards || []), ...taskCards] : (msg.task_cards || [])
                                }
                                : msg
                            )
                        );
                    } else if (data.error) {
                        fullText += `\n\n*[Error: ${data.error}]*`;
                         setMessages((prev) => 
                            prev.map((msg) => 
                                msg.id === assistantId 
                                ? { ...msg, content: fullText, hasError: true } 
                                : msg
                            )
                        );
                    }
                } catch (e) {
                    console.warn("Failed to parse SSE JSON chunk", e);
                }
            }
        }
      }
    } catch (error) {
      console.error('Error in search:', error);
      setMessages((prev) => 
        prev.map((msg) => 
            msg.id === assistantId 
            ? { ...msg, content: msg.content + "\n\n*Sorry, something went wrong.*" } 
            : msg
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)] max-w-5xl mx-auto bg-white rounded-2xl shadow-xl overflow-hidden border border-gray-200">
      {/* Header */}
      <div className="bg-white border-b border-gray-100 p-4 flex items-center justify-between shadow-sm z-10">
        <div>
            <h1 className="text-xl font-bold text-gray-800 tracking-tight">文献搜索</h1>
            <p className="text-xs text-gray-500 mt-0.5">Search Academic Papers & Research</p>
        </div>
        <div className="flex items-center space-x-3">
            <button
              onClick={toggleDebugMode}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                isDebugMode 
                  ? 'bg-amber-100 text-amber-700 border border-amber-300' 
                  : 'bg-gray-100 text-gray-600 border border-gray-200 hover:bg-gray-200'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${isDebugMode ? 'bg-amber-500' : 'bg-gray-400'}`}></span>
              Debug {isDebugMode ? 'ON' : 'OFF'}
            </button>
            <span className={`h-2.5 w-2.5 rounded-full ${isLoading ? 'bg-amber-400 animate-pulse' : 'bg-green-500'}`}></span>
            <span className="text-xs text-gray-500 font-medium">{isLoading ? 'Searching...' : 'Online'}</span>
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 bg-slate-50 scroll-smooth">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-gray-400 space-y-4 opacity-60">
             <div className="w-16 h-16 bg-gray-200 rounded-2xl flex items-center justify-center mb-2">
                <Search size={32} />
             </div>
             <p className="text-lg font-medium">Search for academic papers and research</p>
             <div className="flex gap-2 text-xs">
                <span className="bg-white border px-3 py-1 rounded-full">Machine Learning</span>
                <span className="bg-white border px-3 py-1 rounded-full">AI Safety</span>
                <span className="bg-white border px-3 py-1 rounded-full">Computer Vision</span>
             </div>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} isDebugMode={isDebugMode} />
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="bg-white p-4 border-t border-gray-100">
        <form onSubmit={handleSubmit} className="relative flex items-center max-w-4xl mx-auto">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Search for papers, topics, or research areas..."
            disabled={isLoading}
            className="w-full pl-6 pr-14 py-4 bg-gray-50 border-gray-200 text-gray-900 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all shadow-sm placeholder:text-gray-400"
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className={`
              absolute right-2 p-2.5 rounded-full transition-all duration-200
              ${!input.trim() || isLoading 
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed' 
                : 'bg-blue-600 text-white hover:bg-blue-700 shadow-md hover:shadow-lg transform hover:-translate-y-0.5'
              }
            `}
          >
            {isLoading ? <StopCircle size={20} /> : <Search size={20} />}
          </button>
        </form>
        <div className="text-center mt-2 text-[10px] text-gray-400">
            Search academic papers and research content
        </div>
      </div>
    </div>
  );
};