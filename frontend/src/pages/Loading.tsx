import logoUrl from '../assets/logo.png'

interface LoadingPageProps {
  showLoading?: boolean
}

// Loading 页面 - 支持两种模式：特效模式 和 普通加载模式
export default function LoadingPage({ showLoading = true }: LoadingPageProps) {
  // 普通加载模式 - 简洁样式，无动画
  if (!showLoading) {
    return (
      <div className="min-h-screen bg-[#f5f5f5] flex items-center justify-center">
        <div className="w-5 h-5 border-2 border-gray-300 border-t-green-600 rounded-full animate-spin" />
      </div>
    )
  }

  // 特效加载模式 - 带 logo 背景和呼吸灯效果
  return (
    <div className="min-h-screen bg-[#f5f5f5] flex items-center justify-center relative overflow-hidden">
      {/* Logo 背景 */}
      <div 
        className="absolute inset-0 bg-cover bg-center opacity-90"
        style={{ backgroundImage: `url(${logoUrl})` }}
      />
      
      {/* 中心呼吸亮点 */}
      <div className="relative z-10">
        {/* 内核 */}
        <div className="w-3 h-3 bg-slate-300 rounded-full animate-breathe-core" />
        {/* 光晕层 */}
        <div className="absolute inset-0 w-3 h-3 rounded-full animate-breathe-glow" />
      </div>
      
      {/* 呼吸动画样式 */}
      <style>{`
        @keyframes breathe-core {
          0%, 100% {
            transform: scale(1);
            opacity: 1;
            box-shadow: 0 0 10px 2px rgba(203, 213, 225, 0.8);
          }
          50% {
            transform: scale(1.3);
            opacity: 0.9;
            box-shadow: 0 0 20px 6px rgba(203, 213, 225, 0.6);
          }
        }
        
        @keyframes breathe-glow {
          0%, 100% {
            transform: scale(4);
            opacity: 0.3;
            background: radial-gradient(circle, rgba(203, 213, 225, 0.4) 0%, transparent 60%);
          }
          50% {
            transform: scale(100);
            opacity: 0.02;
            background: radial-gradient(circle, rgba(203, 213, 225, 0.1) 0%, transparent 50%);
          }
        }
        
        .animate-breathe-core {
          animation: breathe-core 2s ease-in-out infinite;
        }
        
        .animate-breathe-glow {
          animation: breathe-glow 2s ease-in-out infinite;
        }
      `}</style>
    </div>
  )
}
