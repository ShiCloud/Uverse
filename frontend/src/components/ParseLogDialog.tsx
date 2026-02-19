import { useState, useEffect, useRef, useCallback } from 'react'
import { 
  Terminal, 
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Wifi,
  WifiOff,
  X,
  Square
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { 
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { getParseLogs, createParseLogsStream, stopParse, type LogEntry, type LogStreamManager } from '../utils/storage_api'

interface ParseLogDialogProps {
  isOpen: boolean
  onClose: () => void
  taskId: string
  filename: string
  status?: 'pending' | 'processing' | 'parsing' | 'completed' | 'failed' | 'stopped'
  onStatusChange?: (status: string) => void
}

// MinerU 后端类型说明：
// - pipeline: 通用解析模式（默认）
// - vlm-auto-engine: 高精度本地推理，Mac 自动使用 MLX
// - hybrid-auto-engine: 下一代高精度本地推理
// 注意: 不支持 vlm-mlx-engine，请使用 vlm-auto-engine

// 日志级别颜色映射
const levelColors: Record<string, string> = {
  'INFO': 'text-gray-300',
  'ERROR': 'text-red-400',
  'WARNING': 'text-yellow-400',
  'DEBUG': 'text-gray-500',
}

export function ParseLogDialog({ 
  isOpen, 
  onClose, 
  taskId, 
  filename,
  status = 'processing',
  onStatusChange
}: ParseLogDialogProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [reconnectAttempt, setReconnectAttempt] = useState(0)
  const [isStopping, setIsStopping] = useState(false)
  const streamManagerRef = useRef<LogStreamManager | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  // 当弹窗打开/关闭时重置 isStopping 和 hasLoadedRef
  useEffect(() => {
    if (isOpen) {
      setIsStopping(false)
    } else {
      // 弹窗关闭时重置 hasLoadedRef，以便下次打开可以重新加载
      hasLoadedRef.current = false
    }
  }, [isOpen])

  // 监听外部 status 变化，当是 stopped 时重置 isStopping
  useEffect(() => {
    if (status === 'stopped') {
      setIsStopping(false)
    }
  }, [status])

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [])

  // 使用 ref 防止 React 18 严格模式下的重复加载
  const hasLoadedRef = useRef(false)

  // 加载历史日志并建立 SSE 连接（打包模式下使用轮询）
  useEffect(() => {
    if (!isOpen || !taskId) return

    // 防止重复加载（React 18 严格模式会挂载组件两次）
    if (hasLoadedRef.current) return
    hasLoadedRef.current = true

    // 重置状态
    setLogs([])
    setReconnectAttempt(0)

    // 首先加载历史日志
    const loadHistoryLogs = async () => {
      try {
        const response = await getParseLogs(taskId, 500)
        setLogs(response.logs)
        setTimeout(scrollToBottom, 100)
      } catch (error) {
        console.error('加载历史日志失败:', error)
      }
    }

    loadHistoryLogs()

    // 检测是否在 Electron 打包环境（使用轮询）
    const isElectronPackaged = window.electronAPI?.isElectron
    
    if (isElectronPackaged) {
      // 打包环境：使用轮询（SSE 在同步解析时无法工作）
      console.log('[ParseLogDialog] Using polling mode for logs')
      setIsConnected(true)
      
      let lastLogCount = 0
      const pollInterval = setInterval(async () => {
        try {
          const response = await getParseLogs(taskId, 1000)
          if (response.logs.length !== lastLogCount) {
            setLogs(response.logs)
            lastLogCount = response.logs.length
          }
        } catch (error) {
          console.error('轮询日志失败:', error)
        }
      }, 2000) // 每 2 秒轮询一次

      return () => {
        clearInterval(pollInterval)
      }
    } else {
      // 开发环境：使用 SSE
      console.log('[ParseLogDialog] Using SSE mode for logs')
      const MAX_LOGS = 5000  // 前端最多保留 5000 条日志
      const streamManager = createParseLogsStream(
        taskId,
        (entry) => {
          setLogs(prev => {
            const newLogs = [...prev, entry]
            // 超过限制时保留最新的日志
            if (newLogs.length > MAX_LOGS) {
              return newLogs.slice(-MAX_LOGS)
            }
            return newLogs
          })
        },
        (error) => {
          console.error('日志流错误:', error)
          setIsConnected(false)
        },
        (attempt) => {
          setReconnectAttempt(attempt)
        }
      )

      streamManagerRef.current = streamManager

      // 定期检查连接状态
      const checkConnection = setInterval(() => {
        setIsConnected(streamManager.isConnected())
      }, 1000)

      return () => {
        clearInterval(checkConnection)
        streamManager.close()
        streamManagerRef.current = null
      }
    }
  }, [isOpen, taskId, scrollToBottom])

  // 自动滚动到底部
  useEffect(() => {
    scrollToBottom()
  }, [logs, scrollToBottom])

  // 手动重连
  const handleReconnect = () => {
    if (streamManagerRef.current) {
      streamManagerRef.current.reconnect()
      setReconnectAttempt(0)
    }
  }

  // 停止解析
  const handleStopParse = async () => {
    if (!taskId || isStopping) return
    
    setIsStopping(true)
    try {
      await stopParse(taskId)
      
      // 添加停止日志
      setLogs(prev => [...prev, {
        timestamp: new Date().toLocaleTimeString(),
        level: 'WARNING',
        message: '用户已停止解析任务'
      }])
      
      // 通知父组件状态变化
      if (onStatusChange) {
        onStatusChange('stopped')
      }
    } catch (error) {
      console.error('停止解析失败:', error)
      setLogs(prev => [...prev, {
        timestamp: new Date().toLocaleTimeString(),
        level: 'ERROR',
        message: `停止解析失败: ${error instanceof Error ? error.message : '未知错误'}`
      }])
      setIsStopping(false)
    }
  }

  // 获取状态图标
  const getStatusIcon = () => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />
      case 'failed':
        return <AlertCircle className="w-5 h-5 text-red-500" />
      case 'stopped':
        return <Square className="w-5 h-5 text-orange-500" />
      case 'processing':
      case 'parsing':
        return <Terminal className="w-5 h-5 text-blue-500" />
      default:
        return <Terminal className="w-5 h-5 text-gray-500" />
    }
  }

  // 获取状态文本
  const getStatusText = () => {
    switch (status) {
      case 'completed':
        return '已完成'
      case 'failed':
        return '失败'
      case 'stopped':
        return '已停止'
      case 'processing':
      case 'parsing':
        return '解析中...'
      default:
        return '等待中'
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl w-[90vw] h-[85vh] p-0 flex flex-col bg-gray-950 border-gray-800" aria-describedby="parse-log-dialog-description">
        <DialogHeader className="px-6 py-4 border-b border-gray-800 flex-shrink-0">
          <DialogDescription id="parse-log-dialog-description" className="sr-only">
            显示 PDF 解析任务的实时日志信息
          </DialogDescription>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {getStatusIcon()}
              <div>
                <DialogTitle className="text-lg font-semibold text-gray-100">
                  解析日志
                </DialogTitle>
                <p className="text-sm text-gray-400 mt-0.5">
                  {filename}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {/* 连接状态 + Task ID */}
              <div className="flex items-center gap-2 text-xs text-gray-500">
                {isConnected ? (
                  <Wifi className="w-3.5 h-3.5 text-green-500" />
                ) : (
                  <WifiOff className="w-3.5 h-3.5 text-red-500" />
                )}
                <span className={isConnected ? 'text-green-500' : 'text-red-500'}>
                  {isConnected ? '已连接' : reconnectAttempt > 0 ? `重连 ${reconnectAttempt}` : '断开'}
                </span>
                <span className="text-gray-600">|</span>
                <span>Task: {taskId}</span>
                {!isConnected && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleReconnect}
                    className="h-6 px-1.5 text-blue-400 hover:text-blue-300 hover:bg-blue-500/10"
                  >
                    <RefreshCw className="w-3 h-3" />
                  </Button>
                )}
              </div>
              
              {/* 状态标签 */}
              <span className={`px-2 py-1 rounded text-xs font-medium ${
                status === 'completed' ? 'bg-green-500/20 text-green-400' :
                status === 'failed' ? 'bg-red-500/20 text-red-400' :
                status === 'stopped' ? 'bg-orange-500/20 text-orange-400' :
                status === 'processing' || status === 'parsing' ? 'bg-blue-500/20 text-blue-400' :
                'bg-gray-500/20 text-gray-400'
              }`}>
                {getStatusText()}
              </span>
              
              {/* 停止按钮 - 解析中或等待中时显示 */}
              {(status === 'processing' || status === 'pending' || status === 'parsing') && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleStopParse}
                  disabled={isStopping}
                  className="h-8 px-3 text-orange-400 hover:text-orange-300 hover:bg-orange-500/10 border border-orange-500/30"
                >
                  {isStopping ? (
                    <RefreshCw className="w-4 h-4 animate-spin mr-1" />
                  ) : (
                    <Square className="w-4 h-4 mr-1" />
                  )}
                  {isStopping ? '停止中...' : '停止解析'}
                </Button>
              )}
              
              {/* 关闭按钮 */}
              <Button
                variant="ghost"
                size="icon"
                onClick={onClose}
                className="h-8 w-8 text-gray-400 hover:text-gray-200 hover:bg-gray-800"
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>

        {/* 日志内容区域 */}
        <div className="flex-1 overflow-auto p-0 font-mono text-sm bg-gray-950">
          {logs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-gray-600">
              <Terminal className="w-12 h-12 mb-3 opacity-50" />
              <p>暂无日志</p>
              <p className="text-xs mt-1">等待解析任务开始...</p>
            </div>
          ) : (
            <div className="py-2">
              {logs.map((log, index) => (
                <div 
                  key={index}
                  className="flex items-start gap-2 px-4 py-0.5 hover:bg-gray-900/50 transition-colors"
                >
                  <span className="text-gray-600 text-xs shrink-0 w-[70px] select-none">
                    {log.timestamp}
                  </span>
                  <span className={`text-xs font-medium shrink-0 w-[50px] select-none ${levelColors[log.level] || 'text-gray-400'}`}>
                    {log.level}
                  </span>
                  <span className="text-gray-300 break-all whitespace-pre-wrap">
                    {log.message}
                  </span>
                </div>
              ))}
              <div ref={logsEndRef} className="h-4" />
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default ParseLogDialog
