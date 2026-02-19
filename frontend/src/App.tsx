import { useState, useEffect } from 'react'
import { HashRouter as Router, Routes, Route, useLocation, useNavigate, Navigate } from 'react-router-dom'
import { 
  FileText, 
  Settings as SettingsIcon, 
  // Database,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import Documents from './pages/Documents'
import Settings from './pages/Settings'
import LoadingPage from './pages/Loading'
import { waitForReady, checkPaths, getConfigValues, getDbStatus } from './utils/api'
import iconImage from './assets/icon.png'

// 侧边栏导航项
interface NavItem {
  id: string
  label: string
  icon: React.ElementType
  path: string
}

const navItems: NavItem[] = [
  { id: 'documents', label: '文档管理', icon: FileText, path: '/documents' },
  // { id: 'knowledge', label: '知识库', icon: Database, path: '/knowledge' },
]

// 左侧边栏组件
function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const isSettingsActive = location.pathname === '/settings'
  // 从 package.json 获取版本号
  const appVersion = __APP_VERSION__

  return (
    <div className="w-16 h-full bg-slate-900 flex flex-col items-center py-4 select-none">
      {/* 应用 Logo */}
      <div className="mb-3 flex flex-col items-center">
        <img 
          src={iconImage} 
          alt="Uverse" 
          className="w-10 h-10 rounded-xl shadow-lg"
        />
      </div>
      <Separator className="w-10 bg-slate-700 mb-4" />

      {/* 主导航 */}
      <div className="flex-1 flex flex-col gap-2 w-full px-2">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path
          const Icon = item.icon
          
          return (
            <Button
              key={item.id}
              variant="ghost"
              onClick={() => navigate(item.path)}
              className={`
                w-full h-auto py-3 px-2 rounded-xl transition-all duration-200 flex flex-col items-center gap-1
                ${isActive 
                  ? 'bg-primary/20 text-primary hover:bg-primary/30' 
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }
              `}
            >
              <Icon className="w-5 h-5" />
              <span className="text-[10px]">{item.label}</span>
            </Button>
          )
        })}
      </div>

      {/* 底部设置 */}
      <div className="mt-auto w-full px-2 flex flex-col items-center gap-2">
        <Button
          variant="ghost"
          className={`
            w-full h-auto py-3 px-2 rounded-xl transition-all duration-200 flex flex-col items-center gap-1
            ${isSettingsActive 
              ? 'bg-primary/20 text-primary hover:bg-primary/30' 
              : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
            }
          `}
          onClick={() => navigate('/settings')}
        >
          <SettingsIcon className="w-5 h-5" />
          <span className="text-[10px]">设置</span>
        </Button>
        {appVersion && <span className="text-[9px] text-slate-500">v{appVersion}</span>}
      </div>
    </div>
  )
}

// 主布局组件
function Layout({ defaultRoute = '/settings' }: { defaultRoute?: string }) {
  return (
    <div className="h-screen w-screen flex overflow-hidden bg-[#f5f5f5]">
      {/* 左侧边栏 */}
      <Sidebar />

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 页面内容 */}
        <main className="flex-1 overflow-hidden">
          <Routes>
            {/* 默认重定向 */}
            <Route path="/" element={<Navigate to={defaultRoute} replace />} />
            
            {/* 文档管理页面 - S3 文件管理 */}
            <Route path="/documents" element={<Documents />} />
            
            {/* 知识库页面 - 暂时隐藏 */}
            {/* <Route path="/knowledge" element={<KnowledgeBase />} /> */}
            
            {/* 设置页面 */}
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

function App() {
  // 服务启动检查状态
  const [isReady, setIsReady] = useState(false)
  // 最小加载时间状态（确保至少显示2秒 loading 页面）
  const [minLoadTimePassed, setMinLoadTimePassed] = useState(false)
  // 是否显示 Loading 特效页面
  const [showLoading, setShowLoading] = useState(true)
  // 路径检查状态 (null = 未检查, true = 有效, false = 无效)
  const [pathsValid, setPathsValid] = useState<boolean | null>(null)
  // 数据库状态 (null = 未检查, true = 可用, false = 不可用)
  const [dbValid, setDbValid] = useState<boolean | null>(null)
  // 数据库模式和信息
  const [dbInfo, setDbInfo] = useState<{ mode?: 'embedded' | 'external'; error?: string }>({})

  // 加载动画默认开启（简化逻辑，移除配置项）
  useEffect(() => {
    setShowLoading(true)
  }, [])

  // 检查服务状态
  useEffect(() => {
    const checkServices = async () => {
      // 延迟2秒后开始，每次间隔2秒，重试5次，与Electron主进程保持一致
      const result = await waitForReady({
        initialDelay: 2000,
        retryDelay: 2000,
        maxRetries: 5
      })

      if (result.ready) {
        setIsReady(true)
        
        // 先获取当前配置
        let configs: Record<string, string> = {}
        try {
          configs = await getConfigValues()
        } catch (error) {
          console.error('[App] 获取配置失败:', error)
        }
        
        // 检查数据库状态
        try {
          const dbStatusResult = await getDbStatus()
          setDbValid(dbStatusResult.available)
          setDbInfo({ mode: dbStatusResult.mode, error: dbStatusResult.error })
          
          if (!dbStatusResult.available) {
            console.warn('[App] 数据库不可用:', dbStatusResult.error)
          }
        } catch (error) {
          console.error('[App] 数据库状态检查异常:', error)
          setDbValid(false)
        }
        
        // 服务就绪后检查关键路径配置（store 和 postgres 是必须的）
        try {
          // 使用配置中的路径值
          const postgresDir = configs.POSTGRES_DIR || 'postgres'
          const storeDir = configs.STORE_DIR || 'store'
          const modelsDir = configs.MODELS_DIR || 'models'
          
          const pathCheckResult = await checkPaths({
            POSTGRES_DIR: postgresDir,
            STORE_DIR: storeDir,
            MODELS_DIR: modelsDir
          })
          
          // 检查关键路径（store、postgres 和 models）
          const isValid = pathCheckResult.valid === true
          setPathsValid(isValid)
          
          if (!isValid) {
            console.warn('[App] 路径检查未通过，错误:', pathCheckResult.errors)
          }
        } catch (error) {
          console.error('[App] 路径检查异常:', error)
          // 检查失败时，默认跳转到设置页面
          setPathsValid(false)
        }
      } else {
        // 服务启动失败（超时或出错），允许进入应用但跳转到设置页面
        console.error('[App] 服务启动失败:', result.error)
        setIsReady(true)
        setMinLoadTimePassed(true)  // 跳过最小加载时间，让用户尽快进入设置页面
        setPathsValid(false)
        setDbValid(false)
        setDbInfo({ mode: 'embedded', error: '服务启动失败: ' + (result.error || '连接超时') })
      }
    }

    checkServices()
  }, [])

  // 最小加载时间计时器（3秒）- 仅在显示 loading 页面时启用
  useEffect(() => {
    if (!showLoading) return
    
    const timer = setTimeout(() => {
      setMinLoadTimePassed(true)
    }, 3000)

    return () => clearTimeout(timer)
  }, [showLoading])

  // 如果服务未就绪或最小加载时间未到，显示 Loading 页面
  if (!isReady || !minLoadTimePassed) {
    return <LoadingPage showLoading={showLoading} />
  }

  // 路径检查或数据库检查完成前继续显示 loading
  if (pathsValid === null || dbValid === null) {
    return <LoadingPage showLoading={showLoading} />
  }

  // 服务就绪且所有检查完成，根据检查结果决定默认页面
  // 路径检查或数据库检查任一失败都跳转到设置页面
  const allValid = pathsValid && dbValid
  const defaultRoute = allValid ? '/documents' : '/settings'
  
  if (!allValid) {
    if (!pathsValid) {
      console.warn('[App] 路径配置检查未通过，跳转到设置页面')
    }
    if (!dbValid) {
      console.warn(`[App] 数据库不可用 (${dbInfo.mode} 模式${dbInfo.error ? ': ' + dbInfo.error : ''})，跳转到设置页面`)
    }
  }
  
  return (
    <Router>
      <Layout defaultRoute={defaultRoute} />
    </Router>
  )
}

export default App
