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
import { waitForReady, getDbStatus } from './utils/api'
import { logger } from './utils/logger'
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
      logger.info('[App] 开始检查服务状态')
      
      // 首先等待服务启动完成（Electron 主进程中的服务启动）
      if (window.electronAPI?.waitForServicesStart) {
        logger.info('[App] 等待服务启动...')
        const startResult = await window.electronAPI.waitForServicesStart()
        logger.info('[App] 服务启动结果:', startResult)
        
        // 保存路径错误到 localStorage
        if (startResult.pathCheck) {
          const pathCheck = startResult.pathCheck
          const pathErrors: Record<string, string> = {}
          
          if (pathCheck.postgres?.valid === false) {
            pathErrors['POSTGRES_DIR'] = pathCheck.postgres.error || 'PostgreSQL 路径无效'
          }
          if (pathCheck.store?.valid === false) {
            pathErrors['STORE_DIR'] = pathCheck.store.error || 'Store 路径无效'
          }
          if (pathCheck.models?.valid === false) {
            pathErrors['MODELS_DIR'] = pathCheck.models.error || 'Models 路径无效'
          }
          
          if (Object.keys(pathErrors).length > 0) {
            localStorage.setItem('path_errors', JSON.stringify(pathErrors))
            setPathsValid(false)
          } else {
            localStorage.removeItem('path_errors')
            setPathsValid(true)
          }
        }
        
        // 如果配置不完整（idle状态），跳转到设置页面
        if (startResult.status === 'idle') {
          logger.info('[App] 配置不完整，跳转到设置页面')
          setPathsValid(false)
          setDbValid(false)
          setServicesReady(true)
          return
        }
        
        // 如果服务启动失败，跳转到设置页面
        if (startResult.status === 'failed') {
          logger.error('[App] 服务启动失败:', startResult.error)
          setPathsValid(false)
          setDbValid(false)
          setServicesReady(true)
          return
        }
      }

      // 服务启动成功，等待后端就绪
      logger.info('[App] 等待后端就绪...')
      const result = await waitForReady({
        initialDelay: 300,
        retryDelay: 500,
        maxRetries: 30
      })

      if (!result.ready) {
        logger.error('[App] 后端未就绪:', result.error)
        setPathsValid(false)
        setDbValid(false)
        setServicesReady(true)
        return
      }

      // 获取数据库状态
      const dbStatusResult = await getDbStatus().catch(err => {
        logger.error('[App] 数据库状态检查异常:', err)
        return { available: false } as DbStatusResult
      })
      
      setDbValid(dbStatusResult.available)
      
      // 所有检查通过
      if (pathsValid === null) {
        setPathsValid(true)
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
  // 跳转到设置页面或文档页面
  const defaultRoute = allValid ? '/documents' : '/settings'
  
  return (
    <Router>
      <Layout defaultRoute={defaultRoute} />
    </Router>
  )
}

export default App
