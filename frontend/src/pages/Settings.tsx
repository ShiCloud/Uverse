import { useEffect, useState, useRef } from 'react'
import { 
  Cpu, 
  Database,
  Settings2,
  Save,
  AlertCircle,
  Key,
  Hash,
  RefreshCw,
  FileText,
  Terminal,
  CheckCircle2,
  FolderOpen,
  Download,
  Folder,
  HardDrive,
  Box,
  Server,
  ToggleLeft,
  Type,
  Lock,
  Globe,
  Zap,
  X,
  Sparkles
} from 'lucide-react'
import { getConfigs, updateConfigs, getConfigCategories, getLogs, getLogLevels, checkPaths, shutdownApp, getDbStatus, testDbConnection } from '../utils/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface ConfigItem {
  key: string
  value: string
  description?: string
  category: string
}

interface LogEntry {
  timestamp: string
  level: string
  message: string
  source?: string
}

function Settings() {
  // 配置管理相关
  const [configs, setConfigs] = useState<ConfigItem[]>([])
  const [categories, setCategories] = useState<Record<string, string>>({})
  const [configLoading, setConfigLoading] = useState(true)
  const [editedValues, setEditedValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [pathErrors, setPathErrors] = useState<Record<string, string>>({})
  const [showRestartDialog, setShowRestartDialog] = useState(false)

  // 从 localStorage 读取保存的设置
  const getSavedLogLevel = () => {
    if (typeof window === 'undefined') return 'INFO'
    return localStorage.getItem('settings_log_level') || 'INFO'
  }
  
  const getSavedLogsHeight = () => {
    if (typeof window === 'undefined') return 384
    const saved = localStorage.getItem('settings_logs_height')
    return saved ? parseInt(saved, 10) : 384
  }
  


  // 日志相关
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [logLevels, setLogLevels] = useState<string[]>(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
  const [selectedLevel, setSelectedLevel] = useState<string>(getSavedLogLevel())


  const [logsError, setLogsError] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [logsHeight, setLogsHeight] = useState(getSavedLogsHeight())
  const logsContainerRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const startYRef = useRef(0)
  const startHeightRef = useRef(0)
  
  // 数据库状态
  const [dbStatus, setDbStatus] = useState<{ available: boolean; mode?: 'embedded' | 'external'; error?: string } | null>(null)
  // 是否隐藏数据库错误提示
  const [hideDbError, setHideDbError] = useState(false)
  // 是否隐藏路径错误提示
  const [hidePathErrors, setHidePathErrors] = useState(false)

  // 密码/密钥类配置项
  const PASSWORD_KEYS = ['OPENAI_API_KEY', 'SECRET_KEY', 'API_KEY', 'TOKEN']
  
  // 路径类配置项（用户需要配置的必要组件路径）
  const PATH_KEYS = ['POSTGRES_DIR', 'STORE_DIR', 'MODELS_DIR', 'MINERU_OUTPUT_DIR']
  
  // 隐藏的配置项（不在界面上显示，但保留配置功能）
  const HIDDEN_KEYS = ['TEMP_DIR', 'APP_VERSION']
  
  // 路径配置项的图标和标题
  const PATH_CONFIG_META: Record<string, { icon: React.ReactNode; title: string; shortTitle: string }> = {
    'POSTGRES_DIR': { 
      icon: <Database className="w-4 h-4 text-blue-500" />, 
      title: 'PostgreSQL 目录',
      shortTitle: 'PostgreSQL'
    },
    'STORE_DIR': { 
      icon: <Folder className="w-4 h-4 text-amber-500" />, 
      title: 'RustFS 存储目录',
      shortTitle: 'RustFS'
    },
    'MODELS_DIR': { 
      icon: <HardDrive className="w-4 h-4 text-purple-500" />, 
      title: 'AI 模型目录',
      shortTitle: 'AI 模型'
    },
    'MINERU_OUTPUT_DIR': { 
      icon: <Box className="w-4 h-4 text-green-500" />, 
      title: '解析输出目录',
      shortTitle: '输出目录'
    }
  }

  // 通用配置项的图标映射
  const CONFIG_ICON_MAP: Record<string, React.ReactNode> = {
    'HOST': <Globe className="w-4 h-4 text-blue-500" />,
    'PORT': <Server className="w-4 h-4 text-green-500" />,
    'LOG_LEVEL': <FileText className="w-4 h-4 text-gray-500" />,
    'USE_EMBEDDED_PG': <ToggleLeft className="w-4 h-4 text-purple-500" />,
    'DATABASE_HOST': <Globe className="w-4 h-4 text-blue-600" />,
    'DATABASE_PORT': <Server className="w-4 h-4 text-green-600" />,
    'DATABASE_USER': <Type className="w-4 h-4 text-gray-600" />,
    'DATABASE_PASSWORD': <Lock className="w-4 h-4 text-red-600" />,
    'DATABASE_NAME': <Database className="w-4 h-4 text-blue-700" />,
    'MINERU_BACKEND': <Zap className="w-4 h-4 text-yellow-500" />,
    'MINERU_DEVICE': <Cpu className="w-4 h-4 text-orange-500" />,
    'MINERU_VRAM': <HardDrive className="w-4 h-4 text-cyan-500" />,
    'MINERU_VIRTUAL_VRAM_SIZE': <HardDrive className="w-4 h-4 text-teal-500" />,
    'OPENAI_API_KEY': <Key className="w-4 h-4 text-amber-600" />,
    'OPENAI_BASE_URL': <Globe className="w-4 h-4 text-indigo-500" />,
    'OPENAI_MODEL': <Box className="w-4 h-4 text-pink-500" />,
    'SECRET_KEY': <Lock className="w-4 h-4 text-red-600" />,

  }

  // 获取配置项的显示名称（简化版）
  const getConfigDisplayName = (key: string): string => {
    const nameMap: Record<string, string> = {
      'HOST': '服务地址',
      'PORT': '服务端口',
      'LOG_LEVEL': '日志级别',
      'USE_EMBEDDED_PG': '使用嵌入式PG',
      'DATABASE_HOST': '主机地址',
      'DATABASE_PORT': '端口',
      'DATABASE_USER': '用户名',
      'DATABASE_PASSWORD': '密码',
      'DATABASE_NAME': '数据库',
      'MINERU_BACKEND': '解析后端',
      'MINERU_DEVICE': '设备模式',
      'MINERU_VRAM': '显存限制',
      'MINERU_VIRTUAL_VRAM_SIZE': '虚拟显存',
      'OPENAI_API_KEY': 'API密钥',
      'OPENAI_BASE_URL': 'API地址',
      'OPENAI_MODEL': '模型名称',
      'SECRET_KEY': '密钥',
    }
    return nameMap[key] || key.replace(/_/g, ' ').toLowerCase()
  }
  
  // 检查路径是否已配置（用于首次使用提示）
  const hasUnconfiguredPaths = () => {
    return PATH_KEYS.some(key => {
      const value = editedValues[key]
      return !value || value.trim() === ''
    })
  }

  // 保存日志级别到 localStorage
  const saveLogLevel = (level: string) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('settings_log_level', level)
    }
  }
  
  // 保存日志高度到 localStorage
  const saveLogsHeight = (height: number) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('settings_logs_height', height.toString())
    }
  }
  


  // 主要配置加载 - 优先执行
  useEffect(() => {
    loadConfigs()
  }, [])

  // 日志加载 - 延迟执行，不阻塞配置显示
  useEffect(() => {
    // 延迟 500ms 加载日志相关数据，确保配置先显示
    const timer = setTimeout(() => {
      loadLogLevels()
      loadInitialLogs(selectedLevel)
      
      // 检测是否在 Electron 打包环境（使用轮询）
      const isElectronPackaged = (window as any).electronAPI?.isElectron
      
      if (isElectronPackaged) {
        // 打包环境：使用 HTTP 轮询
        console.log('[Settings] Using polling mode for logs')
        const pollInterval = setInterval(() => {
          loadInitialLogs(selectedLevel)
        }, 3000)
        
        // 清理函数
        return () => {
          clearInterval(pollInterval)
        }
      } else {
        // 开发环境：使用 WebSocket
        console.log('[Settings] Using WebSocket mode for logs')
        connectWebSocket()
        
        return () => {
          if (wsRef.current) {
            wsRef.current.close()
          }
        }
      }
    }, 500)
    
    return () => clearTimeout(timer)
  }, [])

  // WebSocket 连接 - 使用全局变量确保只有一个实例
  const connectWebSocket = () => {
    // 如果已有连接或正在连接，直接返回
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
      console.debug('[Logs WebSocket] 连接已存在，跳过')
      return
    }
    
    // 使用 window 对象检查全局连接状态（防止 React 严格模式重复渲染）
    if ((window as any).__logsWebSocketConnecting) {
      console.debug('[Logs WebSocket] 全局状态显示正在连接，跳过')
      return
    }
    
    const wsUrl = `ws://localhost:8000/api/logs/ws`
    console.debug('[Logs WebSocket] 正在连接:', wsUrl)
    
    // 设置全局连接状态
    ;(window as any).__logsWebSocketConnecting = true
    
    const ws = new WebSocket(wsUrl)
    
    ws.onopen = () => {
      console.debug('[Logs WebSocket] 已连接')
      setWsConnected(true)
      setLogsError(null)
    }
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        console.debug('[Logs WebSocket] 收到消息:', data.type)
        
        if (data.type === 'log') {
          setLogs(prev => {
            // 检查是否已存在相同日志
            const exists = prev.some(l => 
              l.timestamp === data.timestamp && 
              l.message === data.message && 
              l.level === data.level
            )
            if (exists) return prev
            
            // 限制日志数量，避免内存溢出
            const newLogs = [...prev, {
              timestamp: data.timestamp,
              level: data.level,
              message: data.message,
              source: data.source
            }]
            if (newLogs.length > 1000) {
              return newLogs.slice(-1000)
            }
            return newLogs
          })
        }
        // 忽略 ping 消息
      } catch (error) {
        console.debug('[Logs WebSocket] 解析消息失败:', error)
      }
    }
    
    ws.onerror = (error) => {
      console.debug('[Logs WebSocket] 错误:', error)
      setWsConnected(false)
    }
    
    ws.onclose = (event) => {
      console.debug('[Logs WebSocket] 已断开:', event.code, event.reason)
      setWsConnected(false)
      // 清除全局连接状态
      ;(window as any).__logsWebSocketConnecting = false
      // 3秒后尝试重连
      setTimeout(() => {
        if (document.visibilityState !== 'hidden') {
          connectWebSocket()
        }
      }, 3000)
    }
    
    wsRef.current = ws
  }



  // 加载初始日志（指定级别，默认200条）
  const loadInitialLogs = async (level?: string) => {
    try {
      const params: { limit: number; level: string } = { 
        limit: 200,
        level: level || 'INFO'
      }
      const data = await getLogs(params)
      if (data.success && data.logs) {
        // 正序排列，最新的在后面
        setLogs(data.logs.reverse())
      }
    } catch (error) {
      console.error('加载初始日志失败:', error)
    }
  }

  // 智能滚动：只有在用户查看底部时才自动滚动
  const [isUserAtBottom, setIsUserAtBottom] = useState(true)
  const lastScrollTopRef = useRef(0)
  
  // 检测用户是否滚动到底部（允许 20px 误差）
  const checkIfAtBottom = () => {
    if (!logsContainerRef.current) return true
    const container = logsContainerRef.current
    const threshold = 20
    return (container.scrollHeight - container.scrollTop - container.clientHeight) < threshold
  }
  
  // 处理滚动事件
  const handleScroll = () => {
    if (!logsContainerRef.current) return
    const container = logsContainerRef.current
    const currentScrollTop = container.scrollTop
    
    // 检测滚动方向
    if (currentScrollTop < lastScrollTopRef.current) {
      // 用户向上滚动，标记为不在底部
      setIsUserAtBottom(false)
    } else {
      // 用户向下滚动或保持，检测是否在底部
      const atBottom = checkIfAtBottom()
      setIsUserAtBottom(atBottom)
    }
    
    lastScrollTopRef.current = currentScrollTop
  }
  
  // 自动滚动日志到底部（只在用户在底部时）
  useEffect(() => {
    if (logsContainerRef.current && isUserAtBottom) {
      const container = logsContainerRef.current
      container.scrollTop = container.scrollHeight
    }
  }, [logs, isUserAtBottom])

  // 拖动调整日志高度 - 使用全局事件监听
  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    startYRef.current = e.clientY
    startHeightRef.current = logsHeight
    document.body.style.cursor = 'ns-resize'
    document.body.style.userSelect = 'none'
    
    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientY - startYRef.current
      const newHeight = Math.max(200, Math.min(800, startHeightRef.current + delta))
      setLogsHeight(newHeight)
    }
    
    const handleMouseUp = () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      // 保存高度设置
      saveLogsHeight(startHeightRef.current + (window.event as MouseEvent).clientY - startYRef.current)
    }
    
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }

  const loadConfigs = async (retryCount = 0) => {
    setConfigLoading(true)
    setSaveError(null)
    setHideDbError(false)
    setHidePathErrors(false)
    try {
      // 优先加载配置和分类，数据库状态后台加载
      const [configData, categoryData] = await Promise.all([
        getConfigs(),
        getConfigCategories()
      ])
      
      if (configData.success && configData.configs) {
        setConfigs(configData.configs)
        const initialValues: Record<string, string> = {}
        configData.configs.forEach((config: ConfigItem) => {
          initialValues[config.key] = config.value
        })
        setEditedValues(initialValues)
      } else {
        setSaveError('获取配置失败: ' + (configData.message || '未知错误'))
      }
      
      if (categoryData.categories) {
        setCategories(categoryData.categories)
      }
      
      // 配置加载完成后立即结束 loading 状态
      setConfigLoading(false)
      
      // 数据库状态在后台加载，不阻塞配置显示
      getDbStatus().catch(() => null).then(dbStatusData => {
        if (dbStatusData) {
          setDbStatus(dbStatusData)
        }
      })
    } catch (error: any) {
      console.error('加载配置失败:', error)
      
      // 检查是否是连接错误（后端未就绪）
      const isConnectionError = error.code === 'ECONNREFUSED' || 
                                error.message?.includes('Network Error') ||
                                error.message?.includes('connection refused')
      
      if (isConnectionError && retryCount < 10) {
        // 后端未就绪，显示友好提示并自动重试
        setSaveError('服务正在启动中，请稍候...')
        setTimeout(() => {
          loadConfigs(retryCount + 1)
        }, 2000) // 2秒后重试
        return
      }
      
      setSaveError('加载配置失败: ' + (error.message || '请检查后端服务是否正常运行'))
      setConfigLoading(false)
    }
  }

  const loadLogLevels = async () => {
    try {
      const data = await getLogLevels()
      if (data.levels && data.levels.length > 0) {
        setLogLevels(data.levels)
      }
    } catch (error) {
      console.error('加载日志级别失败:', error)
    }
  }



  // 过滤显示的日志（根据当前选择的级别过滤已加载的日志）
  const filteredLogs = logs.filter(log => {
    const levelOrder: Record<string, number> = { 'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4 }
    const selectedLevelValue = levelOrder[selectedLevel] ?? 1
    const logLevelValue = levelOrder[log.level] ?? 0
    return logLevelValue >= selectedLevelValue
  })

  const handleValueChange = (key: string, value: string) => {
    setEditedValues(prev => ({ ...prev, [key]: value }))
    setSaveSuccess(false)
    // 清除该路径的错误提示
    if (pathErrors[key]) {
      setPathErrors(prev => {
        const newErrors = { ...prev }
        delete newErrors[key]
        return newErrors
      })
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveError(null)
    setSaveSuccess(false)
    setPathErrors({})
    setHidePathErrors(false)
    
    // 收集所有校验错误
    const validationErrors: string[] = []
    const newPathErrors: Record<string, string> = {}
    
    // 检查是否使用嵌入式PG
    const useEmbedded = editedValues['USE_EMBEDDED_PG'] ?? 'true'
    const isEmbedded = useEmbedded.toLowerCase() === 'true'
    
    // ========== 目录配置校验 ==========
    // 收集需要校验的路径
    const pathsToCheck: Record<string, string> = {}
    
    // 校验 POSTGRES_DIR（嵌入式模式必填）
    if (isEmbedded) {
      const pgDir = editedValues['POSTGRES_DIR']?.trim()
      if (!pgDir) {
        validationErrors.push('嵌入式模式必须配置 PostgreSQL 目录')
        newPathErrors['POSTGRES_DIR'] = 'PostgreSQL 目录未配置'
      } else {
        pathsToCheck['POSTGRES_DIR'] = pgDir
      }
    }
    
    // 校验 STORE_DIR（必填）
    const storeDir = editedValues['STORE_DIR']?.trim()
    if (!storeDir) {
      validationErrors.push('必须配置 RustFS 目录')
      newPathErrors['STORE_DIR'] = 'RustFS 目录未配置'
    } else {
      pathsToCheck['STORE_DIR'] = storeDir
    }
    
    // 校验 MODELS_DIR（必填）
    const modelsDir = editedValues['MODELS_DIR']?.trim()
    if (!modelsDir) {
      validationErrors.push('必须配置模型目录')
      newPathErrors['MODELS_DIR'] = 'AI 模型目录未配置'
    } else {
      pathsToCheck['MODELS_DIR'] = modelsDir
    }
    
    // 校验 MINERU_OUTPUT_DIR（输出目录，必填）
    const outputDir = editedValues['MINERU_OUTPUT_DIR']?.trim()
    if (!outputDir) {
      validationErrors.push('必须配置输出目录')
      newPathErrors['MINERU_OUTPUT_DIR'] = '输出目录未配置'
    }
    
    // 一次性检查所有路径
    if (Object.keys(pathsToCheck).length > 0) {
      try {
        const checkResult = await checkPaths(pathsToCheck)
        if (!checkResult.valid) {
          Object.assign(newPathErrors, checkResult.errors)
          if (checkResult.errors['POSTGRES_DIR']) validationErrors.push('PostgreSQL 目录检查失败')
          if (checkResult.errors['STORE_DIR']) validationErrors.push('RustFS 目录检查失败')
          if (checkResult.errors['MODELS_DIR']) validationErrors.push('AI 模型目录检查失败')
        }
      } catch (error: any) {
        console.error('路径校验异常:', error)
        validationErrors.push('路径校验异常: ' + (error.message || '请检查后端服务'))
      }
    }
    
    // ========== 数据库配置校验 ==========
    if (!isEmbedded) {
      const dbHost = editedValues['DATABASE_HOST']?.trim()
      const dbPort = editedValues['DATABASE_PORT']?.trim()
      const dbUser = editedValues['DATABASE_USER']?.trim()
      const dbPassword = editedValues['DATABASE_PASSWORD'] || ''
      const dbName = editedValues['DATABASE_NAME']?.trim()
      
      // 检查必填项
      if (!dbHost) validationErrors.push('数据库主机地址未配置')
      if (!dbPort) validationErrors.push('数据库端口未配置')
      if (!dbUser) validationErrors.push('数据库用户名未配置')
      if (!dbName) validationErrors.push('数据库名称未配置')
      
      // 如果必填项都有，测试连接
      if (dbHost && dbPort && dbUser && dbName) {
        try {
          const testResult = await testDbConnection({
            host: dbHost,
            port: dbPort,
            user: dbUser,
            password: dbPassword,
            database: dbName
          })
          
          if (!testResult.success) {
            validationErrors.push(`数据库连接测试失败: ${testResult.message}`)
          }
        } catch (error: any) {
          validationErrors.push(`数据库连接测试失败: ${error.message || '未知错误'}`)
        }
      }
    }
    
    // ========== 处理校验结果 ==========
    setPathErrors(newPathErrors)
    
    // 分离路径错误和其他错误
    const pathErrorCount = Object.keys(newPathErrors).length
    const otherErrors = validationErrors.filter(err => 
      !err.includes('PostgreSQL') && 
      !err.includes('RustFS') && 
      !err.includes('模型目录')
    )
    
    if (pathErrorCount > 0) {
      // 路径错误只显示在路径配置区域，不显示重复的错误列表
      setSaving(false)
      return
    }
    
    if (otherErrors.length > 0) {
      // 其他错误（如数据库连接失败）显示在保存按钮下方
      setSaveError(otherErrors.join('\n'))
      setSaving(false)
      return
    }
    
    // ========== 执行保存 ==========
    try {
      const result = await updateConfigs(editedValues)
      if (result.success) {
        // 显示重启确认对话框
        setShowRestartDialog(true)
      } else {
        setSaveError(result.message || '保存失败')
      }
    } catch (error: any) {
      console.error('保存配置失败:', error)
      setSaveError(error.response?.data?.detail || error.message || '保存配置失败')
    } finally {
      setSaving(false)
    }
  }

  // 按分类获取配置（过滤掉隐藏的配置项）
  const getConfigsByCategory = (category: string) => {
    return configs.filter((config) => 
      config.category === category && !HIDDEN_KEYS.includes(config.key)
    )
  }

  const isPasswordField = (key: string) => PASSWORD_KEYS.some(pk => key.toUpperCase().includes(pk))

  const isBooleanField = (key: string) => {
    const value = editedValues[key]
    return value?.toLowerCase() === 'true' || value?.toLowerCase() === 'false'
  }

  const getCategoryIcon = (category: string) => {
    switch (category.toLowerCase()) {
      case 'database': return <Database className="w-5 h-5 text-blue-500" />
      case 'server': return <Cpu className="w-5 h-5 text-green-500" />
      case 'openai': return <Sparkles className="w-5 h-5 text-amber-500" />
      case 'mineru': return <Settings2 className="w-5 h-5 text-purple-500" />
      default: return <Settings2 className="w-5 h-5 text-gray-500" />
    }
  }

  const getCategoryTitle = (category: string) => {
    return categories[category] || category
  }

  const getLogLevelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'DEBUG': return 'bg-gray-100 text-gray-600 border-gray-200'
      case 'INFO': return 'bg-blue-100 text-blue-600 border-blue-200'
      case 'WARNING': return 'bg-amber-100 text-amber-600 border-amber-200'
      case 'ERROR': return 'bg-red-100 text-red-600 border-red-200'
      case 'CRITICAL': return 'bg-purple-100 text-purple-600 border-purple-200'
      default: return 'bg-gray-100 text-gray-600 border-gray-200'
    }
  }

  // 渲染配置卡片
  // 渲染路径配置区域 - 横向排列在服务配置上方
  const renderPathConfigs = () => {
    const pathConfigs = configs.filter(c => PATH_KEYS.includes(c.key))
    if (pathConfigs.length === 0) return null

    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {/* 标题 */}
        <div className="flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-b border-gray-200">
          <FolderOpen className="w-5 h-5 text-blue-600" />
          <h3 className="text-base font-semibold text-gray-900">目录配置</h3>
          <span className="text-xs text-gray-500">({pathConfigs.length} 项)</span>
        </div>
        
        {/* 路径配置项 - 横向网格布局 */}
        <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {pathConfigs.map((config) => {
            const meta = PATH_CONFIG_META[config.key]
            const value = editedValues[config.key] ?? config.value
            const isEmpty = !value || value.trim() === ''
            
            return (
              <div key={config.key} className="space-y-2">
                {/* 标签行 */}
                <div className="flex items-center gap-2">
                  {meta?.icon}
                  <Label className="text-sm font-medium text-gray-900">{meta?.shortTitle || config.key}</Label>
                  {isEmpty && (
                    <Badge variant="outline" className="text-xs text-amber-600 border-amber-300 bg-amber-50">
                      未配置
                    </Badge>
                  )}
                </div>
                
                {/* 输入框 */}
                <div className="relative">
                  <Input
                    type="text"
                    value={value}
                    onChange={(e) => handleValueChange(config.key, e.target.value)}
                    className={`w-full font-mono text-xs pr-8 ${isEmpty ? 'border-amber-300 bg-amber-50/30' : ''}`}
                    placeholder="点击输入路径..."
                    title={value} // hover 显示完整路径
                  />
                  {/* 路径状态指示器 */}
                  <div className="absolute right-2 top-1/2 -translate-y-1/2">
                    {isEmpty ? (
                      <AlertCircle className="w-4 h-4 text-amber-500" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4 text-green-500" />
                    )}
                  </div>
                </div>
                
                {/* 描述和错误 */}
                <p className="text-xs text-gray-500 truncate" title={config.description}>
                  {config.description}
                </p>
                
                {/* 路径错误提示 */}
                {pathErrors[config.key] && (
                  <div className="text-xs text-red-500 flex gap-1.5">
                    <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                    <span className="break-all leading-relaxed">{pathErrors[config.key]}</span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // 渲染单个配置项卡片
  const renderConfigCard = (config: ConfigItem) => {
    const icon = CONFIG_ICON_MAP[config.key] || <Hash className="w-4 h-4 text-gray-400" />
    const displayName = getConfigDisplayName(config.key)
    
    return (
      <div key={config.key} className="space-y-2">
        {/* 标签行 */}
        <div className="flex items-center gap-2">
          {icon}
          <Label className="text-sm font-medium text-gray-900">{displayName}</Label>
          {isPasswordField(config.key) && (
            <Lock className="w-3 h-3 text-gray-400" />
          )}
        </div>
        
        {/* 输入框 */}
        <div className="relative">
          {renderCompactConfigInput(config)}
        </div>
        
        {/* 描述 */}
        {config.description && (
          <p className="text-xs text-gray-500 truncate" title={config.description}>
            {config.description}
          </p>
        )}
      </div>
    )
  }

  // 紧凑版配置输入渲染（用于网格布局）
  const renderCompactConfigInput = (config: ConfigItem) => {
    const key = config.key
    const value = editedValues[key] ?? config.value

    // 布尔值字段
    if (isBooleanField(key)) {
      const isChecked = value?.toLowerCase() === 'true'
      return (
        <div className="flex items-center gap-3 h-9">
          <Switch
            checked={isChecked}
            onCheckedChange={(checked) => handleValueChange(key, checked ? 'true' : 'false')}
          />
          <span className="text-sm text-gray-600">{isChecked ? '启用' : '禁用'}</span>
        </div>
      )
    }

    // 下拉选择字段
    if (key === 'LOG_LEVEL') {
      return (
        <Select value={value} onValueChange={(v) => handleValueChange(key, v)}>
          <SelectTrigger className="w-full h-9 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="DEBUG" className="text-xs">DEBUG</SelectItem>
            <SelectItem value="INFO" className="text-xs">INFO</SelectItem>
            <SelectItem value="WARNING" className="text-xs">WARNING</SelectItem>
            <SelectItem value="ERROR" className="text-xs">ERROR</SelectItem>
          </SelectContent>
        </Select>
      )
    }

    // 密码字段
    if (isPasswordField(key)) {
      return (
        <Input
          type="password"
          value={value}
          onChange={(e) => handleValueChange(key, e.target.value)}
          className="w-full h-9 text-xs"
          placeholder="请输入..."
        />
      )
    }

    // 普通文本字段
    return (
      <Input
        type="text"
        value={value}
        onChange={(e) => handleValueChange(key, e.target.value)}
        className="w-full h-9 text-xs"
        placeholder="请输入..."
        title={value}
      />
    )
  }

  // 渲染分类标题旁边的开关控件
  const renderHeaderToggle = (category: string) => {
    if (category === 'database') {
      // 数据库配置 - 使用嵌入式PG开关（紧挨标题显示）
      const useEmbeddedValue = editedValues['USE_EMBEDDED_PG'] ?? 'true'
      const isChecked = useEmbeddedValue.toLowerCase() === 'true'
      return (
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">使用嵌入式PG</span>
          <Switch
            checked={isChecked}
            onCheckedChange={(checked) => handleValueChange('USE_EMBEDDED_PG', checked ? 'true' : 'false')}
            className="data-[state=checked]:bg-blue-500"
          />
        </div>
      )
    }
    return null
  }

  const renderConfigSection = (category: string) => {
    // 过滤掉路径配置项
    let categoryConfigs = getConfigsByCategory(category).filter(
      c => !PATH_KEYS.includes(c.key)
    )
    
    // 数据库配置特殊处理：只显示 DATABASE_ 配置项（嵌入式和外部共用）
    if (category === 'database') {
      // 统一使用 DATABASE_ 前缀的配置项（5项）
      const dbKeys = ['DATABASE_HOST', 'DATABASE_PORT', 'DATABASE_USER', 'DATABASE_PASSWORD', 'DATABASE_NAME']
      const existingKeys = new Set(categoryConfigs.map(c => c.key))
      
      dbKeys.forEach(key => {
        if (!existingKeys.has(key)) {
          categoryConfigs.push({
            key,
            value: editedValues[key] ?? '',
            description: '',
            category: 'database'
          })
        }
      })
      
      categoryConfigs = categoryConfigs.filter(c => dbKeys.includes(c.key))
    }
    
    if (categoryConfigs.length === 0 && category !== 'database') return null

    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {/* 分类标题 */}
        <div className="flex items-center gap-3 px-4 py-3 bg-gray-50 border-b border-gray-200">
          {getCategoryIcon(category)}
          <h3 className="text-base font-semibold text-gray-900">{getCategoryTitle(category)}</h3>
          <span className="text-xs text-gray-500">({categoryConfigs.length} 项)</span>
          {renderHeaderToggle(category)}
        </div>
        
        {/* 配置项网格布局 - 4列横向排列 */}
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {categoryConfigs.map((config) => renderConfigCard(config))}
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* 页面标题 */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">系统设置</h1>
            <p className="text-sm text-gray-500 mt-1">查看系统日志和管理应用配置</p>
          </div>
        </div>

        {/* 系统日志 - 上方 */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200">
          {/* 面板标题 */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <div className="flex items-center gap-3">
              <Terminal className="w-5 h-5 text-purple-500" />
              <h2 className="text-lg font-semibold text-gray-900">系统日志</h2>
            </div>
            <div className="flex items-center gap-2">
              {/* 日志级别过滤 */}
              <Select value={selectedLevel} onValueChange={(v) => { 
                setSelectedLevel(v)
                saveLogLevel(v)
                // 重新加载该级别的日志
                loadInitialLogs(v)
              }}>
                <SelectTrigger className="w-28 h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {logLevels.map((level) => (
                    <SelectItem key={level} value={level} className="text-xs">{level}</SelectItem>
                  ))}
                </SelectContent>
              </Select>


            </div>
          </div>

          {/* 日志内容 - 独立滚动区域 */}
          <div className="flex flex-col">
            {/* 表头 - 固定 */}
            <div className="grid grid-cols-[140px_80px_1fr] gap-2 px-6 py-2 bg-gray-100 border-b border-gray-200 text-xs font-medium text-gray-600">
              <span>时间戳</span>
              <span>级别</span>
              <span>消息</span>
            </div>

            {/* 日志列表 - 独立滚动容器，可调整高度 */}
            <div 
              ref={logsContainerRef}
              onScroll={handleScroll}
              className="overflow-y-auto font-mono text-xs"
              style={{ height: `${logsHeight}px` }}
            >
              {logsError && (
                <Alert variant="destructive" className="m-4">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>{logsError}</AlertDescription>
                </Alert>
              )}

              {filteredLogs.length === 0 && !logsError && (
                <div className="flex flex-col items-center justify-center h-40 text-gray-400">
                  <FileText className="w-12 h-12 mb-2 opacity-50" />
                  <span>暂无日志</span>
                </div>
              )}

              <div>
                {filteredLogs.map((log, index) => (
                  <div key={index} className="grid grid-cols-[140px_80px_1fr] gap-2 px-6 py-1.5 hover:bg-gray-50 border-b border-gray-50 last:border-0">
                    <span className="text-gray-500 truncate">{log.timestamp}</span>
                    <Badge variant="outline" className={`text-xs px-1.5 py-0 h-5 w-fit ${getLogLevelColor(log.level)}`}>
                      {log.level}
                    </Badge>
                    <span className="text-gray-700 truncate" title={log.message}>{log.message}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 底部统计 - 固定 */}
            <div className="px-6 py-2 bg-gray-50 border-t border-gray-200 text-xs text-gray-500 flex items-center justify-between">
              <span>显示 {filteredLogs.length} / {logs.length} 条日志</span>
              <div className="flex items-center gap-3">
                {!isUserAtBottom && (
                  <span className="flex items-center gap-1 text-amber-600">
                    <span className="w-2 h-2 bg-amber-500 rounded-full" />
                    已暂停自动滚动（向下滚动到底部恢复）
                  </span>
                )}
                {isUserAtBottom && wsConnected && (
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                    实时推送中
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* 拖动调整高度条 */}
          <div
            onMouseDown={handleResizeStart}
            className="h-3 bg-gray-100 hover:bg-gray-200 border-t border-b border-gray-200 cursor-ns-resize flex items-center justify-center transition-colors"
            title="拖动调整高度"
          >
            <div className="w-8 h-1 bg-gray-300 rounded-full" />
          </div>
        </div>

        {/* 首次使用提示 */}
        {!configLoading && hasUnconfiguredPaths() && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-amber-800 mb-1">
                  首次使用，请配置必要组件路径
                </h3>
                <p className="text-xs text-amber-700 mb-3">
                  以下组件需要单独下载，请在下方配置它们的安装路径：
                </p>
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-xs text-amber-800">
                    <Database className="w-3.5 h-3.5" />
                    <span className="font-medium">PostgreSQL</span>
                    <span className="text-amber-600">- 数据库服务</span>
                    <button 
                      onClick={() => {
                        if ((window as any).electronAPI?.openExternal) {
                          (window as any).electronAPI.openExternal('https://www.postgresql.org/download/')
                        } else {
                          window.open('https://www.postgresql.org/download/', '_blank')
                        }
                      }}
                      className="text-blue-600 hover:underline ml-auto"
                    >
                      下载 →
                    </button>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-amber-800">
                    <FolderOpen className="w-3.5 h-3.5" />
                    <span className="font-medium">RustFS</span>
                    <span className="text-amber-600">- 文件存储服务</span>
                    <button 
                      onClick={() => {
                        if ((window as any).electronAPI?.openExternal) {
                          (window as any).electronAPI.openExternal('https://github.com/rustfs/rustfs/releases')
                        } else {
                          window.open('https://github.com/rustfs/rustfs/releases', '_blank')
                        }
                      }}
                      className="text-blue-600 hover:underline ml-auto"
                    >
                      下载 →
                    </button>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-amber-800">
                    <Download className="w-3.5 h-3.5" />
                    <span className="font-medium">MinerU Models</span>
                    <span className="text-amber-600">- AI 解析模型 (~5GB)</span>
                    <button 
                      onClick={() => {
                        if ((window as any).electronAPI?.openExternal) {
                          (window as any).electronAPI.openExternal('https://github.com/opendatalab/MinerU')
                        } else {
                          window.open('https://github.com/opendatalab/MinerU', '_blank')
                        }
                      }}
                      className="text-blue-600 hover:underline ml-auto"
                    >
                      下载 →
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 参数配置区域 */}
        <div className="space-y-6">
          {/* 配置标题栏 */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Settings2 className="w-5 h-5 text-blue-500" />
              <h2 className="text-lg font-semibold text-gray-900">参数配置</h2>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={() => loadConfigs()}
                variant="outline"
                size="sm"
                disabled={configLoading}
              >
                <RefreshCw className={`w-4 h-4 mr-1 ${configLoading ? 'animate-spin' : ''}`} />
                刷新
              </Button>
              <Button
                onClick={handleSave}
                disabled={saving || configLoading}
                size="sm"
              >
                {saving ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
                {saving ? '保存中...' : '保存配置'}
              </Button>
            </div>
          </div>

          {/* 提示消息 - 显示非路径错误（如数据库连接失败） */}
          {saveError && Object.keys(pathErrors).length === 0 && (
            <Alert variant="destructive" className="relative pr-10">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <AlertDescription className="whitespace-pre-line">{saveError}</AlertDescription>
              <button
                onClick={() => setSaveError(null)}
                className="absolute top-2 right-2 p-1.5 text-red-600 hover:text-red-800 hover:bg-red-100 rounded-md transition-colors"
                title="关闭提示"
              >
                <X className="w-4 h-4" />
              </button>
            </Alert>
          )}
          
          {saveSuccess && (
            <Alert className="border-green-500 text-green-700 bg-green-50 relative pr-10">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              <AlertDescription>配置保存成功，重启服务后生效</AlertDescription>
              <button
                onClick={() => setSaveSuccess(false)}
                className="absolute top-2 right-2 p-1.5 text-green-600 hover:text-green-800 hover:bg-green-100 rounded-md transition-colors"
                title="关闭提示"
              >
                <X className="w-4 h-4" />
              </button>
            </Alert>
          )}
          
          {/* 路径配置错误提示 */}
          {Object.keys(pathErrors).length > 0 && !hidePathErrors && (
            <Alert variant="destructive" className="border-red-400 bg-red-50 relative pr-10">
              <FolderOpen className="h-4 w-4 flex-shrink-0" />
              <AlertDescription className="flex flex-col gap-1">
                <span className="font-semibold">路径配置检查失败</span>
                <div className="text-sm opacity-90 mt-1 space-y-1">
                  {Object.entries(pathErrors).map(([key, error]) => (
                    <div key={key}>• {error}</div>
                  ))}
                </div>
                <span className="text-sm mt-1">请检查上方的目录配置是否正确。</span>
              </AlertDescription>
              <button
                onClick={() => setHidePathErrors(true)}
                className="absolute top-2 right-2 p-1.5 text-red-600 hover:text-red-800 hover:bg-red-100 rounded-md transition-colors"
                title="关闭提示"
              >
                <X className="w-4 h-4" />
              </button>
            </Alert>
          )}
          
          {/* 数据库连接错误提示 */}
          {dbStatus && !dbStatus.available && !hideDbError && (
            <Alert variant="destructive" className="border-red-400 bg-red-50 relative pr-10">
              <Database className="h-4 w-4" />
              <AlertDescription className="flex flex-col gap-2">
                <span className="font-semibold">
                  {dbStatus.mode === 'external' ? '外部数据库连接失败' : '嵌入式数据库启动失败'}
                </span>
                {dbStatus.error && (
                  <span className="text-sm opacity-90">{dbStatus.error}</span>
                )}
                <div className="text-sm mt-1 space-y-1">
                  {dbStatus.mode === 'external' ? (
                    <span>请检查下方的数据库主机、端口、用户名和密码配置是否正确。</span>
                  ) : (
                    <>
                      <p>请检查以下可能的原因：</p>
                      <ul className="list-disc list-inside space-y-1 ml-2">
                        <li>PostgreSQL 目录配置是否正确（应包含 bin、data 目录）</li>
                        <li>端口 {editedValues['DATABASE_PORT'] || '15432'} 是否被其他程序占用</li>
                        <li>Windows 防火墙是否阻止了本地连接</li>
                        <li>数据目录是否损坏（可尝试删除 postgres/data 目录后重启）</li>
                        <li>是否以管理员身份运行程序</li>
                        <li>是否安装了 VC++ Redistributable（Visual C++ 运行库）</li>
                      </ul>
                      
                      <div className="mt-3 p-2 bg-amber-100 rounded text-xs">
                        <p className="font-semibold text-amber-800">快速修复步骤：</p>
                        <ol className="list-decimal list-inside space-y-0.5 text-amber-800">
                          <li>关闭本应用程序</li>
                          <li>打开文件管理器，进入 PostgreSQL 目录</li>
                          <li>删除或重命名 <code>data</code> 文件夹（如 data_backup）</li>
                          <li>重新启动本应用程序</li>
                        </ol>
                        <p className="mt-1 text-amber-700">程序会自动重新初始化数据库</p>
                      </div>
                    </>
                  )}
                </div>
              </AlertDescription>
              <button
                onClick={() => setHideDbError(true)}
                className="absolute top-2 right-2 p-1.5 text-red-600 hover:text-red-800 hover:bg-red-100 rounded-md transition-colors"
                title="关闭提示"
              >
                <X className="w-4 h-4" />
              </button>
            </Alert>
          )}

          {/* 加载中 */}
          {configLoading && (
            <div className="flex items-center justify-center py-12 bg-white rounded-xl border border-gray-200">
              <RefreshCw className="w-8 h-8 text-gray-400 animate-spin" />
              <span className="ml-3 text-gray-500">加载配置中...</span>
            </div>
          )}

          {/* 配置内容 */}
          {!configLoading && (
            <div className="space-y-6">
              {/* 1. 目录配置 - 横向排列在最上方 */}
              {renderPathConfigs()}
              
              {/* 2. 数据库配置 - 紧跟目录配置 */}
              {renderConfigSection('database')}
              
              {/* 3. 其他配置 */}
              {renderConfigSection('server')}
              {renderConfigSection('mineru')}
            </div>
          )}

          {/* 空状态 */}
          {!configLoading && configs.length === 0 && (
            <div className="text-center py-12 text-gray-500 bg-white rounded-xl border border-gray-200">
              <FileText className="w-12 h-12 mx-auto mb-2 opacity-50" />
              <p>暂无配置项</p>
            </div>
          )}
        </div>

        {/* 页脚 */}
        <div className="text-center text-xs text-gray-400 py-2">Uverse</div>

        {/* 重启确认对话框 */}
        <Dialog open={showRestartDialog} onOpenChange={setShowRestartDialog}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>需要重启程序</DialogTitle>
              <DialogDescription>
                配置已保存，需要重启程序以保证所有服务正确加载。
                <br />
                <br />
                点击"确定"后将关闭应用程序，请手动重新启动。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setShowRestartDialog(false)}
              >
                取消
              </Button>
              <Button
                onClick={async () => {
                  try {
                    await shutdownApp()
                  } catch (error) {
                    console.error('关闭应用失败:', error)
                  }
                  // 无论后端是否成功响应，前端都关闭
                  window.close()
                }}
              >
                确定
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}

export default Settings
