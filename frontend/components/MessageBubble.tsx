import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Message, JsonCard, TaskPayload, SearchResultPayload } from '../types';
import { TaskCard } from './cards/TaskCard';
import { SearchResultCard } from './cards/SearchResultCard';
import { Bot, User, ChevronDown, ChevronRight } from 'lucide-react';

interface MessageBubbleProps {
  message: Message;
  isDebugMode?: boolean;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, isDebugMode = false }) => {
  const isUser = message.role === 'user';
  const [showFunctionCall, setShowFunctionCall] = useState(false);
  const [showFunctionResponse, setShowFunctionResponse] = useState(false);

  const renderCard = (card: JsonCard, index: number) => {
    switch (card.type) {
      case 'task':
        return <TaskCard key={`${card.id}-${index}`} id={card.id} initialData={card.payload as TaskPayload} />;
      case 'search_result':
        return <SearchResultCard key={`${card.id}-${index}`} records={(card.payload as SearchResultPayload).records} query={(card.payload as SearchResultPayload).query} />;
      default:
        return (
          <div key={index} className="p-4 bg-red-50 text-red-600 rounded-md border border-red-200 text-sm mt-2">
            Unsupported Card Type: {card.type}
          </div>
        );
    }
  };

  const formatFunctionDetails = (data: any) => {
    if (!data) return '';
    let details = '';
    
    if (data.name) {
      details += `工具名称: ${data.name}\n\n`;
    }
    
    if (data.arguments) {
      details += `调用参数:\n${JSON.stringify(data.arguments, null, 2)}\n\n`;
    } else if (data.args) {
      details += `调用参数:\n${JSON.stringify(data.args, null, 2)}\n\n`;
    }
    
    if (data.content) {
      details += `响应内容:\n${JSON.stringify(data.content, null, 2)}`;
    } else if (data.response) {
      details += `响应内容:\n${JSON.stringify(data.response, null, 2)}`;
    }
    
    return details;
  };

  // 处理卡片占位符渲染
  const renderCardsPlaceholder = () => {
    const hasAnyCards = (message.search_cards && message.search_cards.length > 0) || 
                       (message.task_cards && message.task_cards.length > 0);
    
    if (hasAnyCards) return null;

    return (
      <div className="w-full max-w-md mt-4 relative overflow-hidden border rounded-2xl p-5 bg-gradient-to-br from-white to-gray-50 border-gray-100 shadow-lg">
        <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/60 to-transparent" />
        <div className="flex items-center gap-4">
          <div className="relative">
            <div className="w-12 h-12 bg-gradient-to-br from-emerald-100 to-emerald-200 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div className="absolute -bottom-1 -right-1 w-4 h-4 bg-blue-500 rounded-full border-2 border-white flex items-center justify-center">
              <div className="w-2 h-2 bg-white rounded-full animate-ping" />
            </div>
          </div>
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-gradient-to-r from-gray-200 to-gray-100 rounded-full w-3/4" />
            <div className="h-3 bg-gradient-to-r from-gray-100 to-gray-50 rounded-full w-1/2" />
          </div>
        </div>
        <div className="mt-4 space-y-3">
          <div className="flex gap-2">
            <div className="h-3 bg-gradient-to-r from-gray-200 to-gray-100 rounded-full flex-1" />
            <div className="h-3 bg-gradient-to-r from-gray-100 to-gray-50 rounded-full w-1/4" />
          </div>
          <div className="h-3 bg-gradient-to-r from-gray-150 to-gray-100 rounded-full w-5/6" />
          <div className="h-3 bg-gradient-to-r from-gray-100 to-gray-50 rounded-full w-2/3" />
        </div>
        <div className="mt-5 pt-4 border-t border-gray-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="relative">
              <svg className="animate-spin h-5 w-5 text-emerald-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            </div>
            <span className="text-sm font-medium bg-gradient-to-r from-emerald-600 to-blue-600 bg-clip-text text-transparent">
              正在加载数据...
            </span>
          </div>
          <div className="flex gap-1">
            <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-2 h-2 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className={`flex w-full mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[90%] md:max-w-[80%] gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${isUser ? 'bg-indigo-600' : 'bg-emerald-600'} text-white`}>
          {isUser ? <User size={16} /> : <Bot size={16} />}
        </div>

        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} min-w-0 overflow-hidden`}>
          <div
            className={`
              px-4 py-3 rounded-2xl text-sm leading-relaxed shadow-sm
              ${isUser
                ? 'bg-indigo-600 text-white rounded-tr-sm'
                : 'bg-white border border-gray-100 text-gray-800 rounded-tl-sm'
              }
            `}
          >
            <div className={`prose ${isUser ? 'prose-invert' : 'prose-slate'} max-w-none break-words`}>
              {message.content.split('[LOADING_CARD]').map((part, idx, arr) => (
                <React.Fragment key={idx}>
                  <ReactMarkdown
                    components={{
                      pre: ({ children }) => <div className="overflow-auto w-full my-2 bg-black/10 p-2 rounded">{children}</div>,
                      code: ({ children }) => <code className="bg-black/10 rounded px-1">{children}</code>
                    }}
                  >
                    {part}
                  </ReactMarkdown>
                  {idx < arr.length - 1 && renderCardsPlaceholder()}
                </React.Fragment>
              ))}
            </div>
          </div>

          {isDebugMode && message.function_call && (
            <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <div 
                className="flex items-center gap-2 cursor-pointer select-none" 
                onClick={() => setShowFunctionCall(!showFunctionCall)}
              >
                <div className="w-5 h-5 bg-blue-500 rounded-full flex items-center justify-center">
                  {showFunctionCall ? (
                    <ChevronDown size={12} className="text-white" />
                  ) : (
                    <ChevronRight size={12} className="text-white" />
                  )}
                </div>
                <span className="text-sm font-medium text-blue-700">调用</span>
                <span className="text-xs text-blue-500 ml-auto">
                  {message.function_call.name || 'Unknown Tool'}
                </span>
              </div>
              {showFunctionCall && (
                <div className="mt-2 pl-7">
                  <pre className="text-xs text-blue-600 bg-blue-100 rounded p-3 overflow-auto max-h-60 whitespace-pre-wrap">
                    {formatFunctionDetails(message.function_call)}
                  </pre>
                </div>
              )}
            </div>
          )}

          {isDebugMode && message.function_response && (
            <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg">
              <div 
                className="flex items-center gap-2 cursor-pointer select-none" 
                onClick={() => setShowFunctionResponse(!showFunctionResponse)}
              >
                <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center">
                  {showFunctionResponse ? (
                    <ChevronDown size={12} className="text-white" />
                  ) : (
                    <ChevronRight size={12} className="text-white" />
                  )}
                </div>
                <span className="text-sm font-medium text-green-700">响应</span>
                <span className="text-xs text-green-500 ml-auto">
                  {message.function_response.name || 'Unknown Tool'}
                </span>
              </div>
              {showFunctionResponse && (
                <div className="mt-2 pl-7">
                  <pre className="text-xs text-green-600 bg-green-100 rounded p-3 overflow-auto max-h-60 whitespace-pre-wrap">
                    {formatFunctionDetails(message.function_response)}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Search Cards Container */}
          {message.search_cards && message.search_cards.length > 0 && (
            <div className={`w-full mt-2 space-y-3 ${isUser ? 'items-end' : 'items-start'}`}>
              {message.search_cards.map((card, idx) => renderCard(card, idx))}
            </div>
          )}

          {/* Task Cards Container */}
          {message.task_cards && message.task_cards.length > 0 && (
            <div className={`w-full mt-2 space-y-3 ${isUser ? 'items-end' : 'items-start'}`}>
              {message.task_cards.map((card, idx) => renderCard(card, idx))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};