import { useState, useEffect } from 'react'
import { HashRouter as Router, Routes, Route, useLocation, useNavigate, Navigate } from 'react-router-dom'
import { 
  FileText, 
  Settings as SettingsIcon, 
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
]

// 左侧边栏组件
function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const isSettingsActive = location.pathname === '/settings'
  const appVersion = __APP_VERSION__

  return (
    <div className="w-16 h-full bg-slate-900 flex flex-col items-center py-4 select-none">
      <div className="mb-3 flex flex-col items-center">
        <img 
          src={iconImage} 
          alt="Uverse" 
          className="w-10 h-10 rounded-xl shadow-lg"
        />
      </div>
      <Separator className="w-10 bg-slate-700 mb-4" />

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
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Navigate to={defaultRoute} replace />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

// 数据库状态类型
interface DbStatusResult {
  available: boolean
  mode?: 'embedded' | 'external'
  error?: string
}

function App() {
  // 路径检查状态
  const [pathsValid, setPathsValid] = useState<boolean | null>(null)
  // 数据库状态
  const [dbValid, setDbValid] = useState<boolean | null>(null)
  // 服务是否就绪
  const [servicesReady, setServicesReady] = useState(false)
  // 最小加载时间是否已过
  const [minLoadTimePassed, setMinLoadTimePassed] = useState(false)

  // 最小加载时间计时器（1秒）
  useEffect(() => {
    const timer = setTimeout(() => {
      setMinLoadTimePassed(true)
    }, 1000)
    return () => clearTimeout(timer)
  }, [])

  // 检查服务状态 - 在Loading页面完成
  useEffect(() => {
    const checkServices = async () => {
      // 等待后端就绪
      const result = await waitForReady({
        initialDelay: 300,
        retryDelay: 500,
        maxRetries: 30
      })

      if (!result.ready) {
        console.error('[App] 服务启动失败:', result.error)
        setPathsValid(false)
        setDbValid(false)
        setServicesReady(true)
        return
      }

      // 并行获取配置和数据库状态
      const [configs, dbStatusResult] = await Promise.all([
        getConfigValues().catch(err => {
          console.error('[App] 获取配置失败:', err)
          return {} as Record<string, string>
        }),
        getDbStatus().catch(err => {
          console.error('[App] 数据库状态检查异常:', err)
          return { available: false } as DbStatusResult
        })
      ])
      
      setDbValid(dbStatusResult.available)
      
      // 检查关键路径配置
      try {
        const configMap = configs as Record<string, string>
        const postgresDir = configMap['POSTGRES_DIR'] || 'postgres'
        const storeDir = configMap['STORE_DIR'] || 'store'
        const modelsDir = configMap['MODELS_DIR'] || 'models'
        
        const pathCheckResult = await checkPaths({
          POSTGRES_DIR: postgresDir,
          STORE_DIR: storeDir,
          MODELS_DIR: modelsDir
        })
        
        setPathsValid(pathCheckResult.valid === true)
      } catch (error) {
        console.error('[App] 路径检查异常:', error)
        setPathsValid(false)
      }
      
      setServicesReady(true)
    }

    checkServices()
  }, [])

  // 服务未就绪或最小加载时间未到，显示 Loading 页面
  if (!servicesReady || !minLoadTimePassed) {
    return <LoadingPage showLoading={true} />
  }

  // 服务就绪且最小加载时间已过，显示主界面
  const allValid = pathsValid === true && dbValid === true
  const defaultRoute = allValid ? '/documents' : '/settings'
  
  return (
    <Router>
      <Layout defaultRoute={defaultRoute} />
    </Router>
  )
}

export default App
