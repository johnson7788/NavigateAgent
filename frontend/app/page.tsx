
'use client';

import { useState, useEffect } from 'react';
import { Search, FileText, Sparkles, ArrowRight, Github, Zap } from 'lucide-react';
import Link from 'next/link';

interface Feature {
  icon: React.ReactNode;
  title: string;
  description: string;
}


export default function Home() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setIsVisible(true), 100);
    return () => clearTimeout(timer);
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      {/* Hero Section */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-16">
        {/* Logo/Brand */}
        <div className={`text-center mb-12 transition-all duration-700 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
          <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 px-4 py-1.5 rounded-full text-sm font-medium mb-6">
            <Zap className="w-4 h-4" />
            AI 智能导航助手
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-900 tracking-tight mb-6">
            学术研究
            <span className="text-blue-600"> AI 智能导航助手</span>
          </h1>
          <p className="text-lg sm:text-xl text-gray-600 max-w-2xl mx-auto leading-relaxed">
            一站式智能学术助手，搜索智能体+触发其它智能体协同完成任务。
          </p>
        </div>

        {/* CTA Button */}
        <div className={`text-center transition-all duration-700 delay-200 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
          <Link
            href="/search"
            className="inline-flex items-center gap-2 bg-blue-600 text-white px-8 py-4 rounded-full text-lg font-semibold hover:bg-blue-700 hover:scale-105 transition-all duration-200 shadow-lg hover:shadow-xl"
          >
            开始体验
            <ArrowRight className="w-5 h-5" />
          </Link>
        </div>

        {/* How it works */}
        <div className={`mt-24 transition-all duration-700 delay-500 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
          <div className="text-center mb-12">
            <h2 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-4">目前功能如下</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 max-w-4xl mx-auto">
            {[
              { step: '01', title: '输入搜索词', desc: '输入你想了解的学术主题或论文关键词' },
              { step: '02', title: '获取结果', desc: 'AI 为你检索相关论文并展示摘要和来源' },
              { step: '03', title: '执行操作', desc: '选择翻译、生成 PPT 等多种后续操作' },
            ].map((item, index) => (
              <div key={index} className="text-center">
                <div className="w-10 h-10 bg-gray-900 text-white rounded-full flex items-center justify-center text-sm font-bold mx-auto mb-4">
                  {item.step}
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{item.title}</h3>
                <p className="text-gray-600 text-sm">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-100 py-8 mt-16">
        <div className="max-w-6xl mx-auto px-4 text-center text-gray-500 text-sm">
          <p>© 2025 智能导航助手 - 让学术研究更简单</p>
        </div>
      </footer>
    </main>
  );
}
