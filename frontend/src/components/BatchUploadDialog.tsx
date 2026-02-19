import { useState, useEffect, useCallback } from 'react'
import { X, FileText, Loader2, CheckCircle2, AlertCircle, Upload } from 'lucide-react'
import { Button } from './ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog'

export interface UploadTask {
  id: string
  file: File
  status: 'pending' | 'uploading' | 'success' | 'error'
  progress: number
  error?: string
}

interface BatchUploadDialogProps {
  isOpen: boolean
  onClose: () => void
  tasks: UploadTask[]
  onRetry: (taskId: string) => void
  onRetryAll: () => void
  onCancel: () => void
}

export function BatchUploadDialog({
  isOpen,
  onClose,
  tasks,
  onRetry,
  onRetryAll,
  onCancel
}: BatchUploadDialogProps) {
  const [canClose, setCanClose] = useState(false)

  const pendingCount = tasks.filter(t => t.status === 'pending' || t.status === 'uploading').length
  const successCount = tasks.filter(t => t.status === 'success').length
  const errorCount = tasks.filter(t => t.status === 'error').length
  const totalCount = tasks.length

  useEffect(() => {
    // 当所有任务完成时，允许关闭
    if (pendingCount === 0 && totalCount > 0) {
      setCanClose(true)
    }
  }, [pendingCount, totalCount])

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const getStatusIcon = (status: UploadTask['status']) => {
    switch (status) {
      case 'pending':
        return <div className="w-5 h-5 rounded-full border-2 border-gray-300" />
      case 'uploading':
        return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
      case 'success':
        return <CheckCircle2 className="w-5 h-5 text-green-500" />
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-500" />
    }
  }

  const getStatusText = (status: UploadTask['status'], progress: number) => {
    switch (status) {
      case 'pending':
        return '等待上传'
      case 'uploading':
        return `上传中 ${progress}%`
      case 'success':
        return '上传成功'
      case 'error':
        return '上传失败'
    }
  }

  const handleClose = useCallback(() => {
    if (canClose || pendingCount === 0) {
      onClose()
    }
  }, [canClose, pendingCount, onClose])

  return (
    <Dialog open={isOpen} onOpenChange={(open) => {
      if (!open && (canClose || pendingCount === 0)) {
        handleClose()
      }
    }}>
      <DialogContent 
        className="max-w-2xl w-[90vw] max-h-[80vh] flex flex-col" 
        aria-describedby="batch-upload-dialog-description"
        hideCloseButton={true}
      >
        <DialogHeader className="flex-shrink-0">
          <DialogDescription id="batch-upload-dialog-description" className="sr-only">
            批量上传文件到文档管理系统
          </DialogDescription>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-lg font-semibold flex items-center gap-2">
              <Upload className="w-5 h-5 text-blue-600" />
              批量上传文件
            </DialogTitle>
            {(canClose || pendingCount === 0) && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={handleClose}
                aria-label="关闭"
              >
                <X className="w-4 h-4" />
              </Button>
            )}
          </div>
        </DialogHeader>

        {/* 总体进度 */}
        <div className="flex-shrink-0 bg-gray-50 rounded-lg p-4 mb-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700">总体进度</span>
            <span className="text-sm text-gray-500">
              {successCount} 成功 / {errorCount} 失败 / {totalCount} 总计
            </span>
          </div>
          <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${((successCount + errorCount) / totalCount) * 100}%` }}
            />
          </div>
          {pendingCount > 0 && (
            <p className="text-xs text-blue-600 mt-2 flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" />
              正在上传 {pendingCount} 个文件...
            </p>
          )}
        </div>

        {/* 文件列表 */}
        <div className="flex-1 overflow-y-auto min-h-0 border border-gray-100 rounded-lg">
          <div className="divide-y divide-gray-100">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
              >
                {/* 状态图标 */}
                <div className="flex-shrink-0">
                  {getStatusIcon(task.status)}
                </div>

                {/* 文件信息 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    <span className="text-sm font-medium text-gray-900 truncate">
                      {task.file.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-gray-500">
                      {formatFileSize(task.file.size)}
                    </span>
                    <span className="text-xs text-gray-400">•</span>
                    <span className={`text-xs ${
                      task.status === 'error' ? 'text-red-500' :
                      task.status === 'success' ? 'text-green-600' :
                      'text-blue-600'
                    }`}>
                      {getStatusText(task.status, task.progress)}
                    </span>
                  </div>
                  {task.error && (
                    <p className="text-xs text-red-500 mt-1">{task.error}</p>
                  )}
                </div>

                {/* 操作按钮 */}
                {task.status === 'error' && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onRetry(task.id)}
                    className="h-7 px-2 text-xs text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                  >
                    重试
                  </Button>
                )}

                {/* 单个进度条（仅上传中显示） */}
                {task.status === 'uploading' && (
                  <div className="w-20 flex-shrink-0">
                    <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500 transition-all duration-300"
                        style={{ width: `${task.progress}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="flex-shrink-0 flex items-center justify-end gap-2 mt-4 pt-4 border-t border-gray-100">
          {errorCount > 0 && pendingCount === 0 && (
            <Button
              variant="outline"
              onClick={onRetryAll}
              className="h-9 px-4"
            >
              重试所有失败
            </Button>
          )}
          {pendingCount > 0 ? (
            <Button
              variant="outline"
              onClick={onCancel}
              className="h-9 px-4 text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              取消上传
            </Button>
          ) : (
            <Button
              onClick={handleClose}
              className="h-9 px-4 bg-blue-600 hover:bg-blue-700 text-white"
            >
              完成
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
