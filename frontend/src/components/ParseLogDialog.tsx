import { useState, useEffect, useRef, useCallback } from 'react'
import { 
  Terminal, 
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  X,
  Square,
  Trash2
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { 
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { getParseLogs, stopParse, type LogEntry } from '../utils/storage_api'

interface ParseLogDialogProps {
  isOpen: boolean
  onClose: () => void
  taskId: string
  filename: string
  status?: 'pending' | 'processing' | 'parsing' | 'completed' | 'failed' | 'stopped'
  onStatusChange?: (status: string) => void
}

// 日志级别颜色映射
const levelColors: Record<string, string> = {
  'INFO': 'text-gray-300',
  'ERROR': 'text-red-400',
  'WARNING': 'text-yellow-400',
  'DEBUG': 'text-gray-500',
}

// 最大保留日志数量（防止内存溢出）
const MAX_LOGS_IN_MEMORY = 5000
// 轮询间隔（毫秒）- 根据状态动态调整
const POLL_INTERVAL_ACTIVE = 1000   // 解析中：1秒
const POLL_INTERVAL_COMPLETED = 5000  // 已完成：5秒

export function ParseLogDialog({ 
  isOpen, 
  onClose, 
  taskId, 
  filename,
  status = 'processing',
  onStatusChange
}: ParseLogDialogProps) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isStopping, setIsStopping] = useState(false)
  const [totalLogs, setTotalLogs] = useState(0)
  const [isTruncated, setIsTruncated] = useState(false)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const lastLogCountRef = useRef(0)

  // 滚动到底部
  const scrollToBottom = useCallback(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [])

  // 加载日志 - 使用增量加载
  const loadLogs = useCallback(async () => {
    if (!taskId || !isOpen) return
    
    try {
      // 计算需要获取的日志数量
      const neededLimit = Math.max(lastLogCountRef.current + 100, 500)
      const response = await getParseLogs(taskId, Math.min(neededLimit, 5000))
      
      setTotalLogs(response.total)
      
      // 如果日志太多，只保留最新的
      let newLogs = response.logs
      if (newLogs.length > MAX_LOGS_IN_MEMORY) {
        newLogs = newLogs.slice(-MAX_LOGS_IN_MEMORY)
        setIsTruncated(true)
      } else {
        setIsTruncated(false)
      }
      
      setLogs(prev => {
        // 只有日志数量变化时才更新
        if (response.logs.length !== lastLogCountRef.current) {
          lastLogCountRef.current = response.logs.length
          return newLogs
        }
        return prev
      })
    } catch (error) {
      console.error('加载日志失败:', error)
    }
  }, [taskId, isOpen])

  // 清空本地日志缓存
  const handleClearLogs = () => {
    setLogs([])
    lastLogCountRef.current = 0
  }

  // 统一管理的轮询 effect - 合并 status 和 isOpen/taskId 的监听
  useEffect(() => {
    if (!isOpen || !taskId) return

    // 只在首次打开时重置状态和加载日志
    if (lastLogCountRef.current === 0) {
      setLogs([])
      setIsTruncated(false)
      loadLogs()
    }
    
    // 清除旧轮询（如果存在）
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
    
    // 根据状态设置轮询间隔
    const interval = (status === 'processing' || status === 'parsing') 
      ? POLL_INTERVAL_ACTIVE 
      : POLL_INTERVAL_COMPLETED
    
    pollIntervalRef.current = setInterval(loadLogs, interval)

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [isOpen, taskId, status, loadLogs])

  // 自动滚动到底部（仅在解析中时）
  useEffect(() => {
    if (status === 'processing' || status === 'parsing') {
      scrollToBottom()
    }
  }, [logs, scrollToBottom, status])

  // 当弹窗打开时重置 isStopping
  useEffect(() => {
    if (isOpen) {
      setIsStopping(false)
    }
  }, [isOpen])

  // 监听外部 status 变化
  useEffect(() => {
    if (status === 'stopped') {
      setIsStopping(false)
    }
  }, [status])

  // 手动刷新
  const handleRefresh = async () => {
    setIsLoading(true)
    await loadLogs()
    setIsLoading(false)
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
        return <Terminal className="w-5 h-5 text-blue-500 animate-pulse" />
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
              {/* 日志统计 */}
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <span>日志: {totalLogs}</span>
                {isTruncated && (
                  <span className="text-yellow-500" title="仅显示最新 5000 条">
                    (已截断)
                  </span>
                )}
                <span className="text-gray-600">|</span>
                <span>Task: {taskId}</span>
              </div>
              
              {/* 清空缓存按钮 */}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClearLogs}
                title="清空本地缓存"
                className="h-8 px-2 text-gray-400 hover:text-gray-200 hover:bg-gray-800"
              >
                <Trash2 className="w-4 h-4" />
              </Button>
              
              {/* 刷新按钮 */}
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRefresh}
                disabled={isLoading}
                className="h-8 px-2 text-gray-400 hover:text-gray-200 hover:bg-gray-800"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              </Button>
              
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
