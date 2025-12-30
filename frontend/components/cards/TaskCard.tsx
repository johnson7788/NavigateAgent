import React, { useEffect, useState, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { TaskPayload } from '../../types';
import { Loader2, CheckCircle2, XCircle, FileBarChart, Languages, ArrowRight, X, FileText, Copy, Check } from 'lucide-react';

interface TaskCardProps {
  id: string;
  initialData: TaskPayload;
}

interface WebSocketMessage {
  task_id: string;
  status: string;
  result?: any;
  message?: string;
  result_url?: string;
  translation_text?: string;  // 翻译结果文本
}

export const TaskCard: React.FC<TaskCardProps> = ({ id, initialData }) => {
  const [data, setData] = useState<TaskPayload>(initialData);
  const dataRef = useRef(data); // 用于在闭包中获取最新状态
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected');
  const [showTranslationModal, setShowTranslationModal] = useState(false);
  const [copied, setCopied] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null);
  const maxReconnectAttempts = 5;
  const reconnectAttempts = useRef(0);

  // 保持 dataRef 与 data 同步
  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  // WebSocket连接函数
  const connectWebSocket = useCallback(() => {
    const taskApiUrl = process.env.NEXT_PUBLIC_API_TASK;
    if (!taskApiUrl) {
      console.error("NEXT_PUBLIC_API_TASK environment variable not found");
      return;
    }

    // 构建WebSocket URL (将http://改为ws://)
    const wsUrl = taskApiUrl.replace('http://', 'ws://').replace('https://', 'wss://');
    const fullWsUrl = `${wsUrl}/ws/${id}`;

    setConnectionStatus('connecting');
    console.log(`Connecting to WebSocket: ${fullWsUrl}`);

    try {
      ws.current = new WebSocket(fullWsUrl);

      ws.current.onopen = () => {
        console.log(`WebSocket connected for task ${id}`);
        setIsConnected(true);
        setConnectionStatus('connected');
        reconnectAttempts.current = 0;
      };

      ws.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          console.log('WebSocket message received:', message);

          if (message.task_id === id) {
            setData(prev => ({
              ...prev,
              status: message.status as TaskPayload['status'],
              ...(message.result && { result: message.result }),
              ...(message.message && { message: message.message }),
              ...(message.result_url && { result_url: message.result_url }),
              ...(message.translation_text && { translation_text: message.translation_text })
            }));
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.current.onclose = (event) => {
        console.log(`WebSocket disconnected for task ${id}`, event.code, event.reason);
        setIsConnected(false);
        setConnectionStatus('disconnected');

        // 清理重连定时器
        if (reconnectTimeout.current) {
          clearTimeout(reconnectTimeout.current);
          reconnectTimeout.current = null;
        }

        // 使用 ref 获取最新状态，避免闭包中的 stale data
        if (dataRef.current.status === 'done' || dataRef.current.status === 'failed') {
          console.log(`Task ${id} already ${dataRef.current.status}, not attempting reconnect`);
          return;
        }

        // 任务未完成，尝试重连
        if (reconnectAttempts.current < maxReconnectAttempts) {
          reconnectAttempts.current++;
          console.log(`Attempting to reconnect (${reconnectAttempts.current}/${maxReconnectAttempts})...`);

          reconnectTimeout.current = setTimeout(() => {
            connectWebSocket();
          }, 2000 * reconnectAttempts.current);
        } else {
          // 重连次数用完，设置任务状态为 failed
          console.log(`Max reconnect attempts reached for task ${id}`);
          setData(prev => ({
            ...prev,
            status: 'failed',
            message: prev.message || '连接超时，请刷新页面重试'
          }));
        }
      };

      ws.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionStatus('error');
        // 注意：WebSocket 错误不应该直接改变任务状态
        // 任务状态应该由服务器通过 onmessage 发送的消息来更新
        // onclose 会在连接真正关闭后处理重连逻辑
      };

    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setConnectionStatus('error');
    }
  }, [id, data.status]);

  // 初始化WebSocket连接
  useEffect(() => {
    if (data.status === 'done' || data.status === 'failed') {
      return;
    }

    connectWebSocket();

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [id, data.status, connectWebSocket]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'text-blue-600 bg-blue-50 border-blue-200';
      case 'done': return 'text-green-600 bg-green-50 border-green-200';
      case 'failed': return 'text-red-600 bg-red-50 border-red-200';
      default: return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const getConnectionStatusColor = () => {
    switch (connectionStatus) {
      case 'connected': return 'text-green-500';
      case 'connecting': return 'text-yellow-500';
      case 'error': return 'text-red-500';
      case 'disconnected': return 'text-gray-500';
      default: return 'text-gray-500';
    }
  };

  const getConnectionStatusText = () => {
    switch (connectionStatus) {
      case 'connected': return '实时连接';
      case 'connecting': return '连接中...';
      case 'error': return '连接错误';
      case 'disconnected': return '已断开';
      default: return '未知状态';
    }
  };

  const getIcon = () => {
    if (data.status === 'running' || data.status === 'accepted') return <Loader2 className="animate-spin" size={20} />;
    if (data.status === 'done') return <CheckCircle2 size={20} />;
    if (data.status === 'failed') return <XCircle size={20} />;
    return <Loader2 size={20} />;
  };

  const getToolIcon = () => {
    if (data.tool === 'translator') return <Languages size={18} />;
    return <FileBarChart size={18} />;
  }

  // 预处理翻译文本，处理未被 $ 包裹的 LaTeX 命令
  const preprocessTranslationText = (text: string): string => {
    if (!text) return '';

    // 将常见的未包裹 LaTeX 符号转换为对应的 Unicode 字符
    const latexToUnicode: Record<string, string> = {
      '\\upbeta': 'β',
      '\\beta': 'β',
      '\\alpha': 'α',
      '\\gamma': 'γ',
      '\\delta': 'δ',
      '\\mu': 'μ',
      '\\sigma': 'σ',
      '\\omega': 'ω',
      '\\pm': '±',
      '\\times': '×',
      '\\div': '÷',
      '\\leq': '≤',
      '\\geq': '≥',
      '\\neq': '≠',
      '\\approx': '≈',
      '\\infty': '∞',
    };

    let processed = text;

    // 替换常见的 LaTeX 符号为 Unicode
    for (const [latex, unicode] of Object.entries(latexToUnicode)) {
      // 匹配未被 $ 包裹的 LaTeX 命令（后面跟着空格、标点或行尾）
      const regex = new RegExp(latex.replace(/\\/g, '\\\\') + '(?![a-zA-Z])', 'g');
      processed = processed.replace(regex, unicode);
    }

    // 移除其他未识别的反斜杠命令，只保留命令名（如 \mathsf{A} -> A）
    processed = processed.replace(/\\mathsf\{([^}]+)\}/g, '$1');
    processed = processed.replace(/\\mathbf\{([^}]+)\}/g, '$1');
    processed = processed.replace(/\\mathrm\{([^}]+)\}/g, '$1');
    processed = processed.replace(/\\tt\{([^}]+)\}/g, '$1');
    processed = processed.replace(/\\textit\{([^}]+)\}/g, '$1');
    processed = processed.replace(/\\textbf\{([^}]+)\}/g, '$1');

    // 处理下标和上标：\upbeta_{2} -> β₂
    processed = processed.replace(/_\{([^}]+)\}/g, (_, content) => {
      const subscripts: Record<string, string> = {
        '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
        '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
        'a': 'ₐ', 'e': 'ₑ', 'i': 'ᵢ', 'o': 'ₒ', 'n': 'ₙ', 'r': 'ᵣ'
      };
      return content.split('').map((c: string) => subscripts[c] || c).join('');
    });

    // 移除剩余的反斜杠（保留内容）
    processed = processed.replace(/\\([a-zA-Z]+)/g, '$1');

    return processed;
  };

  // 复制翻译内容到剪贴板
  const handleCopyTranslation = async () => {
    if (data.translation_text) {
      try {
        await navigator.clipboard.writeText(data.translation_text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error('Failed to copy:', err);
      }
    }
  };

  const handleCardClick = () => {
    // PPT 结果：打开预览或下载
    if (data.result_url) {
      if (data.result_url.endsWith('.pptx') || data.result_url.endsWith('.ppt')) {
        const previewUrl = `https://view.officeapps.live.com/op/view.aspx?src=${encodeURIComponent(data.result_url)}`;
        window.open(previewUrl, '_blank');
      } else {
        window.open(data.result_url, '_blank');
      }
    }
    // 翻译结果：显示美观的模态框
    else if (data.translation_text) {
      setShowTranslationModal(true);
    }
    else {
      console.log(`Navigating to /task/${id}`);
    }
  };

  return (
    <div
      onClick={handleCardClick}
      className={`w-full max-w-md mt-4 border rounded-xl p-4 cursor-pointer hover:shadow-md transition-all duration-200 ${getStatusColor(data.status)} bg-opacity-40 border-opacity-60`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-white rounded-lg shadow-sm">
            {getToolIcon()}
          </div>
          <div>
            <h4 className="font-semibold text-sm capitalize">{data.tool.replace('_', ' ')} Task</h4>
            <span className="text-xs opacity-70 font-mono">ID: {id.slice(0, 8)}...</span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-white bg-opacity-60 shadow-sm`}>
            {getIcon()}
            <span className="capitalize">{data.status}</span>
          </div>
          {data.status !== 'done' && data.status !== 'failed' && (
            <div className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-white bg-opacity-40 shadow-sm ${getConnectionStatusColor()}`}>
              <div className={`w-2 h-2 rounded-full ${connectionStatus === 'connected' ? 'bg-green-500' : connectionStatus === 'connecting' ? 'bg-yellow-500 animate-pulse' : connectionStatus === 'error' ? 'bg-red-500' : 'bg-gray-400'}`}></div>
              <span className="text-xs">{getConnectionStatusText()}</span>
            </div>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <div className="text-sm opacity-90">
          {data.message}
        </div>

        {/* Progress Bar */}
        {(data.status === 'running' || data.status === 'accepted') && (
          <div className="w-full bg-gray-200 rounded-full h-1.5 dark:bg-gray-700 overflow-hidden">
            <div
              className="bg-current h-1.5 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${Math.max(5, data.progress * 100)}%` }}
            ></div>
          </div>
        )}

        {/* Action / Result */}
        {data.status === 'done' && (
          <div className="flex items-center text-sm font-medium mt-2 bg-white bg-opacity-50 p-2 rounded-lg justify-between group">
            <span>View Result</span>
            <ArrowRight size={16} className="transform group-hover:translate-x-1 transition-transform" />
          </div>
        )}
      </div>

      {/* 翻译结果模态框 */}
      {showTranslationModal && data.translation_text && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowTranslationModal(false);
          }}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[85vh] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 模态框头部 */}
            <div className="flex items-center justify-between p-5 border-b bg-gradient-to-r from-blue-50 to-indigo-50">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-blue-100 rounded-xl">
                  <FileText className="text-blue-600" size={22} />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-800">论文翻译结果</h3>
                  <div className="flex items-center gap-4 text-sm text-gray-500 mt-1">
                    <span className="flex items-center gap-1">
                      <span className="font-medium text-blue-600">{data.translation_text.length.toLocaleString()}</span> 字符
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setShowTranslationModal(false)}
                className="p-2 hover:bg-gray-100 rounded-full transition-colors"
              >
                <X size={20} className="text-gray-500" />
              </button>
            </div>

            {/* 模态框内容 */}
            <div className="flex-1 overflow-y-auto p-6">
              <div className="prose prose-sm max-w-none prose-p:my-2 prose-headings:mt-4 prose-headings:mb-2">
                <ReactMarkdown
                  remarkPlugins={[remarkMath]}
                  rehypePlugins={[[rehypeKatex, {
                    throwOnError: false,
                    strict: false,
                    output: 'htmlAndMathml'
                  }]]}
                  components={{
                    p: ({ children }) => <p className="text-gray-700 leading-relaxed text-base my-2">{children}</p>,
                    h1: ({ children }) => <h1 className="text-xl font-bold text-gray-800 mt-4 mb-2">{children}</h1>,
                    h2: ({ children }) => <h2 className="text-lg font-semibold text-gray-800 mt-3 mb-2">{children}</h2>,
                    h3: ({ children }) => <h3 className="text-base font-medium text-gray-800 mt-2 mb-1">{children}</h3>,
                  }}
                >
                  {preprocessTranslationText(data.translation_text || '')}
                </ReactMarkdown>
              </div>
            </div>

            {/* 模态框底部 */}
            <div className="flex items-center justify-between p-4 border-t bg-gray-50">
              <div className="text-sm text-gray-500">
                💡 提示：可滚动查看全文
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleCopyTranslation}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${copied
                    ? 'bg-green-100 text-green-700'
                    : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
                    }`}
                >
                  {copied ? <Check size={16} /> : <Copy size={16} />}
                  {copied ? '已复制' : '复制全文'}
                </button>
                <button
                  onClick={() => setShowTranslationModal(false)}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  关闭
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
