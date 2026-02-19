import { useState, useEffect, useRef, useCallback } from 'react'
import { 
  FileText, 
  Trash2, 
  Eye,
  Upload,
  CheckCircle2,
  Loader2,
  AlertCircle,
  Play,
  Search,
  X,
  FileType,
  Calendar,
  HardDrive,
  Download,
  Maximize2,
  Minimize2,
  Terminal,
  RefreshCw,
  Edit3,
  Save,
  Square,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { 
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Pagination } from '@/components/ui/pagination'
import { BatchUploadDialog, UploadTask } from '@/components/BatchUploadDialog'
import { 
  uploadDocument, 
  startParse, 
  getParseStatus,
  listFiles,
  getFileDetail,
  getFileContent,
  deleteFile,
  downloadMarkdownWithImages,
  updateFileContent,
  FileListResponse
} from '../utils/storage_api'
import { ParseLogDialog } from '../components/ParseLogDialog'

// 文件接口
interface StorageFile {
  id: string
  filename: string
  file_type: string
  size: number
  bucket: string
  object_key: string
  s3_url: string
  status: string
  created_at: string
  doc_id?: string
  related_files?: Array<{
    id: string
    filename: string
    file_type: string
    s3_url: string
  }>
}

// 文件详情接口
interface FileDetail {
  id: string
  filename: string
  file_type: string
  mime_type: string
  size: number
  bucket: string
  object_key: string
  s3_url: string
  doc_id: string
  status: string
  meta_data?: any
  created_at: string
  updated_at: string
  related_files?: Array<{
    id: string
    filename: string
    file_type: string
    size: number
    status: string
    created_at: string
    s3_url: string
  }>
}

// Markdown 渲染组件
interface MarkdownRendererProps {
  content: string
}

function MarkdownRenderer({ content }: MarkdownRendererProps) {
  // 简单的 Markdown 渲染
  const renderMarkdown = (text: string) => {
    // 转义 HTML 特殊字符
    const escapeHtml = (str: string) => {
      return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
    }

    // 处理代码块
    let html = text.replace(/```([\s\S]*?)```/g, (_, code) => {
      return `<pre class="bg-gray-100 p-3 rounded-lg overflow-x-auto my-3 text-sm font-mono">${escapeHtml(code)}</pre>`
    })

    // 处理行内代码
    html = html.replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono text-red-600">$1</code>')

    // 处理标题
    html = html.replace(/^### (.*$)/gim, '<h3 class="text-lg font-bold mt-4 mb-2 text-gray-900">$1</h3>')
    html = html.replace(/^## (.*$)/gim, '<h2 class="text-xl font-bold mt-5 mb-3 text-gray-900">$1</h2>')
    html = html.replace(/^# (.*$)/gim, '<h1 class="text-2xl font-bold mt-6 mb-4 text-gray-900">$1</h1>')

    // 处理粗体和斜体
    html = html.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>')
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold">$1</strong>')
    html = html.replace(/\*(.*?)\*/g, '<em class="italic">$1</em>')

    // 处理图片 - 使用实际 img 标签显示
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, url) => {
      return `<div class="my-4">
        <img src="${url}" alt="${alt}" class="max-w-full h-auto rounded-lg shadow-sm border border-gray-200" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
        <div class="hidden items-center justify-center p-4 bg-gray-50 rounded-lg border border-gray-200 text-gray-400 text-sm">
          <span>图片加载失败</span>
        </div>
        ${alt ? `<p class="text-xs text-gray-500 mt-2 text-center">${alt}</p>` : ''}
      </div>`
    })

    // 处理链接
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:underline">$1</a>')

    // 处理无序列表
    html = html.replace(/^\s*[-*+]\s+(.+)$/gim, '<li class="ml-4 my-1">$1</li>')
    html = html.replace(/(<li[^>]*>.*<\/li>\n?)+/g, '<ul class="list-disc my-3 text-gray-700">$&</ul>')

    // 处理有序列表
    html = html.replace(/^\s*\d+\.\s+(.+)$/gim, '<li class="ml-4 my-1">$1</li>')
    html = html.replace(/(<li[^>]*>.*<\/li>\n?)+/gs, (matchList) => {
      if (matchList.includes('list-disc')) return matchList
      return `<ol class="list-decimal my-3 text-gray-700">${matchList}</ol>`
    })

    // 处理分隔线
    html = html.replace(/^---+$/gim, '<hr class="my-6 border-gray-200" />')

    // 处理引用块
    html = html.replace(/^>\s*(.+)$/gim, '<blockquote class="border-l-4 border-gray-300 pl-4 my-3 text-gray-600 italic">$1</blockquote>')

    // 处理段落（简单的换行处理）
    const paragraphs = html.split('\n\n')
    html = paragraphs.map(p => {
      const trimmed = p.trim()
      if (!trimmed) return ''
      // 如果已经包含 HTML 标签，不再包裹
      if (trimmed.startsWith('<') && trimmed.endsWith('>')) return trimmed
      // 处理单个换行为 <br>
      return `<p class="my-2 text-gray-700 leading-relaxed">${trimmed.replace(/\n/g, '<br/>')}</p>`
    }).join('\n')

    return html
  }

  return (
    <div 
      className="prose prose-sm max-w-none text-gray-800"
      dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
    />
  )
}

// 预览弹窗组件
interface PreviewDialogProps {
  isOpen: boolean
  onClose: () => void
  file: StorageFile | null
}

function PreviewDialog({ isOpen, onClose, file }: PreviewDialogProps) {
  const [, setFileDetail] = useState<FileDetail | null>(null)
  const [pdfContent, setPdfContent] = useState<string>('')
  const [mdContent, setMdContent] = useState<string>('')
  const [mdFileInfo, setMdFileInfo] = useState<{id: string, filename: string} | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [maximizedPanel, setMaximizedPanel] = useState<'none' | 'pdf' | 'markdown'>('none')
  
  // 编辑相关状态
  const [isEditing, setIsEditing] = useState(false)
  const [editedContent, setEditedContent] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(true) // 编辑时是否显示预览
  
  // 判断文件类型
  const isPdfFile = (filename: string) => filename.toLowerCase().endsWith('.pdf')
  const isWordFile = (filename: string) => filename.toLowerCase().endsWith('.docx')
  const isTextFile = (filename: string) => filename.toLowerCase().endsWith('.txt')
  const isCsvFile = (filename: string) => filename.toLowerCase().endsWith('.csv')

  useEffect(() => {
    if (isOpen && file) {
      loadFileDetail()
    } else {
      // 关闭时重置状态
      setFileDetail(null)
      setPdfContent('')
      setMdContent('')
      setMdFileInfo(null)
      setMaximizedPanel('none')
      // 重置编辑状态
      setIsEditing(false)
      setEditedContent('')
      setSaveError(null)
    }
  }, [isOpen, file])

  const loadFileDetail = async () => {
    if (!file) return
    
    setIsLoading(true)
    try {
      const detail = await getFileDetail(file.id)
      setFileDetail(detail)
      
      // 获取原始PDF内容（通过iframe显示）
      setPdfContent(detail.s3_url)
      
      // 如果有解析后的markdown文件，获取内容
      if (detail.related_files && detail.related_files.length > 0) {
        const mdFile = detail.related_files.find((f: {filename: string, file_type: string}) => 
          f.filename.endsWith('.md') || f.file_type === 'markdown'
        )
        if (mdFile) {
          try {
            const content = await getFileContent(mdFile.id)
            setMdContent(content.content || '')
            // 初始化编辑内容
            setEditedContent(content.content || '')
            // 保存 markdown 文件信息供下载和编辑使用
            setMdFileInfo({ id: mdFile.id, filename: mdFile.filename })
          } catch (e) {
            console.error('获取Markdown内容失败:', e)
            setMdContent('获取Markdown内容失败')
            setEditedContent('')
            setMdFileInfo(null)
          }
        } else {
          setMdFileInfo(null)
        }
      } else {
        setMdFileInfo(null)
      }
    } catch (error) {
      console.error('获取文件详情失败:', error)
    } finally {
      setIsLoading(false)
    }
  }

  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const hasMarkdown = mdContent.length > 0

  // 切换最大化状态
  const toggleMaximize = (panel: 'pdf' | 'markdown') => {
    if (maximizedPanel === panel) {
      setMaximizedPanel('none')
    } else {
      setMaximizedPanel(panel)
    }
  }

  // 开始编辑
  const handleStartEdit = () => {
    setEditedContent(mdContent)
    setIsEditing(true)
    setSaveError(null)
    // 自动最大化 Markdown 区域
    setMaximizedPanel('markdown')
  }

  // 取消编辑
  const handleCancelEdit = () => {
    setEditedContent(mdContent)
    setIsEditing(false)
    setSaveError(null)
  }

  // 保存编辑
  const handleSaveEdit = async () => {
    if (!mdFileInfo?.id) return
    
    setIsSaving(true)
    setSaveError(null)
    
    try {
      const result = await updateFileContent(mdFileInfo.id, editedContent)
      console.log('[PreviewDialog] 保存成功:', result)
      
      // 更新本地内容
      setMdContent(editedContent)
      setIsEditing(false)
      
      // 显示成功提示
      alert('保存成功！')
    } catch (error) {
      console.error('[PreviewDialog] 保存失败:', error)
      setSaveError(error instanceof Error ? error.message : '保存失败')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-7xl w-[95vw] h-[90vh] p-0 flex flex-col" aria-describedby="preview-dialog-description">
        <DialogHeader className="px-6 py-4 border-b border-gray-200 flex-shrink-0">
          <DialogDescription id="preview-dialog-description" className="sr-only">
            预览文档内容，PDF 文件支持解析为 Markdown，其他文件支持下载查看
          </DialogDescription>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <DialogTitle className="text-lg font-semibold text-gray-900">
                {file?.filename}
              </DialogTitle>
              {file && (
                <div className="flex items-center gap-3 text-sm text-gray-500">
                  <span className="flex items-center gap-1">
                    <HardDrive className="w-4 h-4" />
                    {formatFileSize(file.size)}
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="w-4 h-4" />
                    {new Date(file.created_at).toLocaleString('zh-CN')}
                  </span>
                </div>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* 内容区域 */}
        <div className="flex-1 overflow-hidden bg-gray-50">
          {isLoading ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="w-8 h-8 text-gray-400 animate-spin" />
            </div>
          ) : file && !isPdfFile(file.filename) ? (
            // 非 PDF 文件：显示下载视图
            <div className="h-full flex items-center justify-center p-8">
              <div className="text-center max-w-md">
                <div className="w-20 h-20 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
                  {isWordFile(file.filename) && <FileType className="w-10 h-10 text-blue-600" />}
                  {isTextFile(file.filename) && <FileType className="w-10 h-10 text-gray-500" />}
                  {isCsvFile(file.filename) && <FileType className="w-10 h-10 text-green-600" />}
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  {isWordFile(file.filename) && 'Word 文档'}
                  {isTextFile(file.filename) && '文本文件'}
                  {isCsvFile(file.filename) && 'CSV 文件'}
                </h3>
                <p className="text-gray-500 mb-6">
                  该类型文件不支持在线预览，请下载后查看
                </p>
                <div className="flex items-center justify-center gap-3">
                  <Button
                    onClick={() => file && downloadFile(file.s3_url, file.filename)}
                    className="h-10 px-6 bg-blue-600 hover:bg-blue-700 text-white"
                  >
                    <Download className="w-4 h-4 mr-2" />
                    下载文件
                  </Button>
                </div>
                <div className="mt-6 text-xs text-gray-400">
                  <p>文件名: {file.filename}</p>
                  <p>大小: {formatFileSize(file.size)}</p>
                </div>
              </div>
            </div>
          ) : (
            // PDF 文件：显示双栏预览
            <div className="h-full flex">
              {/* 左侧：PDF 预览 */}
              <div 
                className={`h-full transition-all duration-300 ${
                  maximizedPanel === 'pdf' ? 'flex-1' : 
                  maximizedPanel === 'markdown' ? 'hidden' : 
                  hasMarkdown ? 'w-1/2 border-r border-gray-200' : 'flex-1'
                }`}
              >
                <div className="h-full flex flex-col">
                  <div className="px-4 py-2 bg-gray-100 border-b border-gray-200 flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700">原始 PDF</span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => file && downloadFile(file.s3_url, file.filename)}
                        className="p-1 hover:bg-gray-200 rounded transition-colors"
                        title="下载 PDF"
                      >
                        <Download className="w-4 h-4 text-gray-600" />
                      </button>
                      <button
                        onClick={() => toggleMaximize('pdf')}
                        className="p-1 hover:bg-gray-200 rounded transition-colors"
                        title={maximizedPanel === 'pdf' ? '恢复双栏' : '最大化'}
                      >
                        {maximizedPanel === 'pdf' ? (
                          <Minimize2 className="w-4 h-4 text-gray-600" />
                        ) : (
                          <Maximize2 className="w-4 h-4 text-gray-600" />
                        )}
                      </button>
                    </div>
                  </div>
                  <div className="flex-1 overflow-hidden relative">
                    {pdfContent ? (
                      <iframe
                        src={pdfContent}
                        className="w-full h-full border-0"
                        title="PDF Preview"
                        style={{ backgroundColor: '#f5f5f5' }}
                      />
                    ) : (
                      <div className="h-full flex items-center justify-center text-gray-400">
                        无法加载 PDF
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* 右侧：Markdown 预览或提示 */}
              {maximizedPanel === 'pdf' ? (
                // PDF 最大化时，右侧隐藏
                null
              ) : !hasMarkdown ? (
                // 没有 Markdown：右侧显示提示
                <div className="w-80 h-full bg-gray-50 border-l border-gray-200 flex items-center justify-center p-6">
                  <div className="text-center">
                    <FileType className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                    <p className="text-gray-500 text-sm mb-2">尚未解析</p>
                    <p className="text-gray-400 text-xs">
                      点击"解析"按钮将 PDF 转换为 Markdown
                    </p>
                  </div>
                </div>
              ) : (
                // 显示 Markdown
                <div 
                  className={`h-full transition-all duration-300 ${
                    maximizedPanel === 'markdown' ? 'flex-1' : 'w-1/2 border-l border-gray-200'
                  }`}
                >
                  <div className="h-full flex flex-col">
                    <div className="px-4 py-2 bg-gray-100 border-b border-gray-200 flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-700">
                        {isEditing ? '编辑 Markdown' : '解析结果 (Markdown)'}
                      </span>
                      <div className="flex items-center gap-2">
                        {/* 字符数显示 */}
                        <span className="text-xs text-gray-500">
                          {(isEditing ? editedContent : mdContent).length.toLocaleString()} 字符
                        </span>
                        
                        {/* 编辑/保存/取消按钮 */}
                        {isEditing ? (
                          <>
                            {/* 预览切换按钮 */}
                            <button
                              onClick={() => setShowPreview(!showPreview)}
                              className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
                                showPreview 
                                  ? 'bg-blue-100 text-blue-700 hover:bg-blue-200' 
                                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                              }`}
                              title={showPreview ? '隐藏预览' : '显示预览'}
                            >
                              <Eye className="w-3 h-3" />
                              {showPreview ? '预览中' : '预览'}
                            </button>
                            {/* 最大化/最小化按钮 */}
                            <button
                              onClick={() => toggleMaximize('markdown')}
                              className="flex items-center gap-1 px-2 py-1 bg-gray-100 hover:bg-gray-200 text-gray-600 text-xs rounded transition-colors"
                              title={maximizedPanel === 'markdown' ? '恢复双栏' : '最大化'}
                            >
                              {maximizedPanel === 'markdown' ? (
                                <>
                                  <Minimize2 className="w-3 h-3" />
                                  恢复
                                </>
                              ) : (
                                <>
                                  <Maximize2 className="w-3 h-3" />
                                  全屏
                                </>
                              )}
                            </button>
                            <button
                              onClick={handleSaveEdit}
                              disabled={isSaving}
                              className="flex items-center gap-1 px-2 py-1 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white text-xs rounded transition-colors"
                              title="保存"
                            >
                              {isSaving ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                              ) : (
                                <Save className="w-3 h-3" />
                              )}
                              保存
                            </button>
                            <button
                              onClick={handleCancelEdit}
                              disabled={isSaving}
                              className="flex items-center gap-1 px-2 py-1 bg-gray-500 hover:bg-gray-600 disabled:bg-gray-400 text-white text-xs rounded transition-colors"
                              title="取消"
                            >
                              <X className="w-3 h-3" />
                              取消
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={handleStartEdit}
                            className="flex items-center gap-1 px-2 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded transition-colors"
                            title="编辑"
                          >
                            <Edit3 className="w-3 h-3" />
                            编辑
                          </button>
                        )}
                        
                        {/* 预览/下载按钮 */}
                        {!isEditing && (
                          <>
                            <button
                              onClick={() => {
                                // 使用已保存的 markdown 文件信息
                                if (mdFileInfo?.id) {
                                  const zipFilename = `${mdFileInfo.filename.replace('.md', '')}.zip`
                                  downloadMarkdownWithImages(mdFileInfo.id, zipFilename)
                                    .catch(error => {
                                      console.error('下载失败:', error)
                                      alert('下载失败: ' + error.message)
                                    })
                                } else {
                                  console.error('Markdown file not available')
                                  alert('下载链接不可用，请稍后重试')
                                }
                              }}
                              className="p-1 hover:bg-gray-200 rounded transition-colors"
                              title="下载 Markdown（含图片）"
                            >
                              <Download className="w-4 h-4 text-gray-600" />
                            </button>
                            <button
                              onClick={() => toggleMaximize('markdown')}
                              className="p-1 hover:bg-gray-200 rounded transition-colors"
                              title={maximizedPanel === 'markdown' ? '恢复双栏' : '最大化'}
                            >
                              {maximizedPanel === 'markdown' ? (
                                <Minimize2 className="w-4 h-4 text-gray-600" />
                              ) : (
                                <Maximize2 className="w-4 h-4 text-gray-600" />
                              )}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    
                    {/* 错误提示 */}
                    {saveError && (
                      <div className="px-4 py-2 bg-red-50 border-b border-red-200">
                        <p className="text-xs text-red-600 flex items-center gap-1">
                          <AlertCircle className="w-3 h-3" />
                          {saveError}
                        </p>
                      </div>
                    )}
                    
                    <div className="flex-1 overflow-auto">
                      {isEditing ? (
                        // 编辑器模式：分屏显示编辑器和预览
                        <div className="h-full flex">
                          {/* 左侧：编辑器 */}
                          <div className={`h-full ${showPreview ? 'w-1/2 border-r border-gray-200' : 'w-full'}`}>
                            <textarea
                              value={editedContent}
                              onChange={(e) => setEditedContent(e.target.value)}
                              className="w-full h-full p-4 font-mono text-sm text-gray-800 bg-white resize-none focus:outline-none"
                              placeholder="在此编辑 Markdown 内容..."
                              spellCheck={false}
                            />
                          </div>
                          {/* 右侧：实时预览 */}
                          {showPreview && (
                            <div className="w-1/2 h-full overflow-auto p-4 bg-gray-50">
                              <div className="text-xs text-gray-400 mb-2 border-b border-gray-200 pb-1 flex items-center gap-1">
                                <Eye className="w-3 h-3" />
                                实时预览
                              </div>
                              {editedContent ? (
                                <MarkdownRenderer content={editedContent} />
                              ) : (
                                <div className="text-gray-400 text-sm">
                                  开始输入以查看预览...
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ) : (
                        // 预览模式
                        <div className="p-4">
                          {mdContent ? (
                            <MarkdownRenderer content={mdContent} />
                          ) : (
                            <div className="h-full flex items-center justify-center text-gray-400">
                              暂无解析内容
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// 下载文件到本地
async function downloadFile(url: string, filename: string) {
  try {
    // 获取文件内容
    const response = await fetch(url, {
      method: 'GET',
      mode: 'cors',
      credentials: 'omit',
    })
    if (!response.ok) {
      throw new Error(`下载失败: ${response.status}`)
    }
    
    // 获取 blob
    const blob = await response.blob()
    
    // 创建临时链接
    const downloadUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = downloadUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    
    // 清理
    document.body.removeChild(link)
    window.URL.revokeObjectURL(downloadUrl)
  } catch (error) {
    console.error('下载失败:', error)
    alert('下载失败，请重试')
  }
}

// 解析状态轮询管理器
class ParseStatusPoller {
  private docId: string
  private onStatusChange: (status: string) => void
  private onError: (error: string) => void
  private intervalId: number | null = null
  private retryCount = 0
  private maxRetries = 5
  private isRunning = false

  constructor(
    docId: string,
    _filename: string,
    onStatusChange: (status: string) => void,
    onError: (error: string) => void
  ) {
    this.docId = docId
    this.onStatusChange = onStatusChange
    this.onError = onError
  }

  start() {
    if (this.isRunning) return
    this.isRunning = true
    this.retryCount = 0
    this.poll()
  }

  stop() {
    this.isRunning = false
    if (this.intervalId !== null) {
      clearTimeout(this.intervalId)
      this.intervalId = null
    }
  }

  private async poll() {
    if (!this.isRunning) return

    try {
      const status = await getParseStatus(this.docId)
      this.onStatusChange(status.status)
      
      // 重置重试计数
      this.retryCount = 0
      
      // 如果解析完成、失败或已停止，停止轮询
      if (status.status === 'completed' || status.status === 'failed' || status.status === 'stopped') {
        this.stop()
        return
      }
      
      // 继续轮询
      this.intervalId = window.setTimeout(() => this.poll(), 2000)
    } catch (error) {
      console.error('获取解析状态失败:', error)
      this.retryCount++
      
      if (this.retryCount >= this.maxRetries) {
        this.onError('获取解析状态失败，请手动刷新页面查看结果')
        this.stop()
        return
      }
      
      // 使用指数退避策略
      const delay = Math.min(2000 * Math.pow(2, this.retryCount - 1), 30000)
      this.intervalId = window.setTimeout(() => this.poll(), delay)
    }
  }
}

function Documents() {
  // 文件列表状态
  const [files, setFiles] = useState<StorageFile[]>([])
  const [filteredFiles, setFilteredFiles] = useState<StorageFile[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalItems, setTotalItems] = useState(0)
  const [totalPages, setTotalPages] = useState(1)

  // 批量上传状态
  const [uploadTasks, setUploadTasks] = useState<UploadTask[]>([])
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false)
  const [, setIsUploading] = useState(false)

  // 预览弹窗状态
  const [previewFile, setPreviewFile] = useState<StorageFile | null>(null)
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)

  // 日志弹窗状态
  const [logDialogState, setLogDialogState] = useState<{
    isOpen: boolean
    taskId: string
    filename: string
    status: 'pending' | 'processing' | 'parsing' | 'completed' | 'failed' | 'stopped'
  }>({
    isOpen: false,
    taskId: '',
    filename: '',
    status: 'pending'
  })

  // 活跃的解析轮询器
  const pollersRef = useRef<Map<string, ParseStatusPoller>>(new Map())

  // 加载文件列表（支持分页）
  const loadFiles = useCallback(async (page: number = currentPage, size: number = pageSize) => {
    setIsLoading(true)
    try {
      const data: FileListResponse = await listFiles('upload', page, size)
      setFiles(data.files)
      setFilteredFiles(data.files)
      setTotalItems(data.total)
      setTotalPages(data.total_pages)
      setCurrentPage(data.page)
      setPageSize(data.page_size)
    } catch (error) {
      console.error('加载文件列表失败:', error)
    } finally {
      setIsLoading(false)
    }
  }, [currentPage, pageSize])

  useEffect(() => {
    loadFiles()
  }, [])

  // 组件卸载时清理轮询器
  useEffect(() => {
    return () => {
      pollersRef.current.forEach(poller => poller.stop())
      pollersRef.current.clear()
    }
  }, [])

  // 搜索过滤（在客户端过滤当前页数据）
  const handleSearch = useCallback(() => {
    if (!searchQuery.trim()) {
      setFilteredFiles(files)
      return
    }
    
    const query = searchQuery.toLowerCase().trim()
    const keywords = query.split(/\s+/).filter(k => k.length > 0)
    const filtered = files.filter(file => {
      const filename = file.filename.toLowerCase()
      return keywords.every(keyword => filename.includes(keyword))
    })
    setFilteredFiles(filtered)
  }, [searchQuery, files])

  // 回车搜索
  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  // 页码变化
  const handlePageChange = (page: number) => {
    setCurrentPage(page)
    loadFiles(page, pageSize)
  }

  // 每页数量变化
  const handlePageSizeChange = (size: number) => {
    setPageSize(size)
    setCurrentPage(1)
    loadFiles(1, size)
  }

  // 文件上传处理 - 批量上传
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return

    const files = Array.from(e.target.files)
    
    // 打印选择的文件信息
    files.forEach(file => {
      console.log(`[FileSelect] 文件: ${file.name}, 类型: ${file.type}, 大小: ${file.size} bytes`)
    })
    
    // 创建上传任务
    const newTasks: UploadTask[] = files.map(file => ({
      id: Math.random().toString(36).substring(7),
      file,
      status: 'pending',
      progress: 0
    }))

    setUploadTasks(newTasks)
    setIsUploadDialogOpen(true)
    setIsUploading(true)

    // 开始批量上传
    startBatchUpload(newTasks)

    // 清空文件输入
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // 批量上传逻辑
  const startBatchUpload = async (tasks: UploadTask[]) => {
    const maxConcurrent = 2 // 降低并发数，避免超时
    let completedCount = 0
    const totalTasks = tasks.length

    const uploadSingle = async (task: UploadTask) => {
      // 更新任务状态为上传中
      setUploadTasks(prev => prev.map(t => 
        t.id === task.id ? { ...t, status: 'uploading', progress: 10 } : t
      ))

      try {
        console.log(`[Upload] 开始上传: ${task.file.name}, 大小: ${task.file.size} bytes, 类型: ${task.file.type}`)
        
        await uploadDocument(task.file, {
          timeout: 300000, // 5 分钟超时
        })
        
        console.log(`[Upload] 上传成功: ${task.file.name}`)
        
        // 上传成功
        setUploadTasks(prev => prev.map(t => 
          t.id === task.id ? { ...t, status: 'success', progress: 100 } : t
        ))
      } catch (error) {
        // 上传失败
        const errorMsg = error instanceof Error ? error.message : '上传失败'
        console.error(`[Upload] 上传失败: ${task.file.name}, 错误: ${errorMsg}`)
        setUploadTasks(prev => prev.map(t => 
          t.id === task.id ? { ...t, status: 'error', error: errorMsg } : t
        ))
      } finally {
        completedCount++
        
        // 所有任务完成
        if (completedCount === totalTasks) {
          setIsUploading(false)
          // 刷新文件列表
          loadFiles()
        }
      }
    }

    // 使用队列控制并发
    const queue = [...tasks]
    const running: Promise<void>[] = []
    
    const processQueue = async () => {
      while (queue.length > 0) {
        if (running.length < maxConcurrent) {
          const task = queue.shift()!
          const promise = uploadSingle(task).then(() => {
            const index = running.indexOf(promise)
            if (index > -1) {
              running.splice(index, 1)
            }
          })
          running.push(promise)
        } else {
          // 等待任意一个任务完成
          await Promise.race(running)
        }
      }
      // 等待所有剩余任务完成
      if (running.length > 0) {
        await Promise.all(running)
      }
    }
    
    await processQueue()
  }

  // 重试单个上传任务
  const handleRetryUpload = (taskId: string) => {
    const task = uploadTasks.find(t => t.id === taskId)
    if (!task) return

    setUploadTasks(prev => prev.map(t => 
      t.id === taskId ? { ...t, status: 'uploading', progress: 0, error: undefined } : t
    ))

    uploadDocument(task.file)
      .then(() => {
        setUploadTasks(prev => prev.map(t => 
          t.id === taskId ? { ...t, status: 'success', progress: 100 } : t
        ))
        loadFiles()
      })
      .catch((error) => {
        const errorMsg = error instanceof Error ? error.message : '上传失败'
        setUploadTasks(prev => prev.map(t => 
          t.id === taskId ? { ...t, status: 'error', error: errorMsg } : t
        ))
      })
  }

  // 重试所有失败的上传任务
  const handleRetryAllUploads = () => {
    const failedTasks = uploadTasks.filter(t => t.status === 'error')
    failedTasks.forEach(task => handleRetryUpload(task.id))
  }

  // 取消上传
  const handleCancelUpload = () => {
    // 关闭对话框，但保留任务状态
    setIsUploadDialogOpen(false)
    setIsUploading(false)
  }

  // 打开预览弹窗
  const handlePreview = (file: StorageFile) => {
    setPreviewFile(file)
    setIsPreviewOpen(true)
  }

  // 关闭预览弹窗
  const handleClosePreview = () => {
    setIsPreviewOpen(false)
    setPreviewFile(null)
  }

  // 删除文件
  const handleDeleteFile = async (fileId: string) => {
    if (!confirm('确定要删除这个文件吗？相关的转换文件也会被删除。')) {
      return
    }
    
    try {
      await deleteFile(fileId)
      await loadFiles()
      // 如果删除的是当前预览的文件，关闭预览
      if (previewFile?.id === fileId) {
        handleClosePreview()
      }
    } catch (error) {
      console.error('删除失败:', error)
      alert('删除失败: ' + (error as Error).message)
    }
  }

  // 打开日志弹窗
  const openLogDialog = (docId: string, filename: string, status: 'pending' | 'processing' | 'parsing' | 'completed' | 'failed' | 'stopped') => {
    setLogDialogState({
      isOpen: true,
      taskId: docId,
      filename,
      status
    })
  }

  // 关闭日志弹窗
  const closeLogDialog = () => {
    setLogDialogState(prev => ({ ...prev, isOpen: false }))
  }

  // 处理日志弹窗状态变化
  const handleLogDialogStatusChange = (status: string) => {
    setLogDialogState(prev => ({
      ...prev,
      status: status as 'pending' | 'processing' | 'completed' | 'failed' | 'stopped'
    }))
    
    // 停止对应的轮询器
    if (logDialogState.taskId) {
      const poller = pollersRef.current.get(logDialogState.taskId)
      if (poller) {
        poller.stop()
        pollersRef.current.delete(logDialogState.taskId)
      }
    }
    
    // 刷新文件列表以显示最新状态
    loadFiles()
  }

  // 解析 PDF
  const handleParse = async (docId: string, filename: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await startParse(docId, filename)
      // 打开日志弹窗
      openLogDialog(docId, filename, 'processing')
      
      // 使用轮询器监控解析状态
      const poller = new ParseStatusPoller(
        docId,
        filename,
        (newStatus) => {
          // 状态变化时刷新文件列表
          loadFiles()
          
          // 更新日志弹窗状态 - 使用函数式更新避免闭包问题
          setLogDialogState(prev => {
            if (prev.taskId === docId) {
              return {
                ...prev,
                status: newStatus as 'pending' | 'processing' | 'parsing' | 'completed' | 'failed' | 'stopped'
              }
            }
            return prev
          })
          
          // 如果完成、失败或已停止，移除轮询器
          if (newStatus === 'completed' || newStatus === 'failed' || newStatus === 'stopped') {
            pollersRef.current.delete(docId)
          }
        },
        (error) => {
          console.error('解析状态监控失败:', error)
        }
      )
      
      pollersRef.current.set(docId, poller)
      poller.start()
    } catch (error) {
      console.error('启动解析失败:', error)
      alert('启动解析失败: ' + (error as Error).message)
    }
  }

  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  // 获取状态显示
  const getStatusDisplay = (status: string, filename: string) => {
    // 判断是否是 PDF 文件
    const isPdf = filename.toLowerCase().endsWith('.pdf')
    
    switch (status) {
      case 'completed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-xs">
            <CheckCircle2 className="w-3 h-3" />
            {isPdf ? '已解析' : '已上传'}
          </span>
        )
      case 'processing':
      case 'parsing':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 text-xs">
            <Loader2 className="w-3 h-3 animate-spin" />
            解析中
          </span>
        )
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs">
            {isPdf ? '待解析' : '待处理'}
          </span>
        )
      case 'failed':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-xs">
            <AlertCircle className="w-3 h-3" />
            失败
          </span>
        )
      case 'stopped':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 text-xs">
            <Square className="w-3 h-3" />
            已停止
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs">
            {status}
          </span>
        )
    }
  }

  // 获取文件图标
  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase()
    if (ext === 'pdf') return <FileType className="w-5 h-5 text-red-500" />
    if (ext === 'md' || ext === 'markdown') return <FileType className="w-5 h-5 text-blue-500" />
    if (ext === 'txt') return <FileType className="w-5 h-5 text-gray-500" />
    if (ext === 'docx') return <FileType className="w-5 h-5 text-blue-600" />
    if (ext === 'csv') return <FileType className="w-5 h-5 text-green-600" />
    return <FileText className="w-5 h-5 text-gray-500" />
  }

  return (
    <div className="h-full flex flex-col bg-[#f5f5f5]">
      {/* 顶部工具栏 */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          {/* 左侧：标题和搜索栏 */}
          <div className="flex items-center gap-4 flex-1">
            {/* 文档管理标题 */}
            <div className="flex items-center gap-2 text-slate-800">
              <FileText className="w-6 h-6 text-primary" />
              <h1 className="text-xl font-semibold">文档管理</h1>
            </div>
            
            {/* 搜索栏 */}
            <div className="flex items-center gap-2 flex-1 max-w-xl">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <Input
                  type="text"
                  placeholder="搜索文件名..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={handleSearchKeyDown}
                  className="pl-10 pr-4 h-10 bg-gray-50 border-gray-200 focus:bg-white"
                />
                {searchQuery && (
                  <button
                    onClick={() => {
                      setSearchQuery('')
                      setFilteredFiles(files)
                    }}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
              <Button
                onClick={handleSearch}
                variant="secondary"
                className="h-10 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700"
              >
                查询
              </Button>
              <Button
                onClick={() => loadFiles()}
                variant="ghost"
                size="icon"
                className="h-10 w-10 text-gray-500 hover:text-blue-600"
                title="刷新"
              >
                <RefreshCw className="w-4 h-4" />
              </Button>
            </div>
          </div>

          {/* 右侧：上传按钮和统计 */}
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-500">
              共 <span className="font-medium text-gray-900">{totalItems}</span> 个文件
            </span>
            
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileSelect}
              accept=".pdf,.docx,.txt,.csv"
              className="hidden"
              id="file-upload"
              multiple
            />
            <label htmlFor="file-upload">
              <Button
                asChild
                className="h-10 px-4 bg-green-600 hover:bg-green-700 text-white"
              >
                <span className="flex items-center gap-2 cursor-pointer">
                  <Upload className="w-4 h-4" />
                  上传文件
                </span>
              </Button>
            </label>
          </div>
        </div>
      </div>

      {/* 文件列表区域 */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-6xl mx-auto">
          {isLoading ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 py-16 text-center">
              <Loader2 className="w-8 h-8 text-gray-400 animate-spin mx-auto mb-4" />
              <p className="text-gray-500">加载中...</p>
            </div>
          ) : filteredFiles.length === 0 ? (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 py-16 text-center">
              <div className="w-20 h-20 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <FileText className="w-10 h-10 text-gray-300" />
              </div>
              <p className="text-gray-500 mb-1">
                {searchQuery ? '未找到匹配的文件' : '暂无文件'}
              </p>
              <p className="text-sm text-gray-400">
                {searchQuery ? '请尝试其他搜索词' : '点击上方"上传文件"按钮添加文档'}
              </p>
            </div>
          ) : (
            <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
              {/* 表头 */}
              <div className="grid grid-cols-[1fr_100px_100px_140px] gap-3 px-6 py-3 bg-gray-50 border-b border-gray-100 text-sm font-medium text-gray-600">
                <div>文件名</div>
                <div>大小</div>
                <div>状态</div>
                <div className="text-center">操作</div>
              </div>

              {/* 文件列表 */}
              <div className="divide-y divide-gray-100">
                {filteredFiles.map((file) => (
                  <div 
                    key={file.id}
                    className="grid grid-cols-[1fr_100px_100px_140px] gap-3 px-6 py-4 items-center hover:bg-gray-50 transition-colors"
                  >
                    {/* 文件名 */}
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 bg-gray-100 rounded-lg flex items-center justify-center shrink-0">
                        {getFileIcon(file.filename)}
                      </div>
                      <div className="min-w-0">
                        <a 
                          href={file.s3_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-gray-900 hover:text-blue-600 truncate block"
                          title={file.filename}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {file.filename}
                        </a>
                        <p className="text-xs text-gray-400">
                          {new Date(file.created_at).toLocaleString('zh-CN')}
                        </p>
                      </div>
                    </div>

                    {/* 大小 */}
                    <div className="text-sm text-gray-600">
                      {formatFileSize(file.size)}
                    </div>

                    {/* 状态 */}
                    <div>
                      {getStatusDisplay(file.status, file.filename)}
                    </div>

                    {/* 操作按钮 */}
                    <div className="flex items-center justify-end gap-1">
                      {/* 解析按钮 - 对PDF且未解析、解析失败或已停止的文件显示 */}
                      {file.filename.toLowerCase().endsWith('.pdf') && (file.status === 'pending' || file.status === 'failed' || file.status === 'stopped') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={(e) => handleParse(file.doc_id!, file.filename, e)}
                          className={`h-8 px-2 ${file.status === 'failed' || file.status === 'stopped' ? 'text-orange-600 hover:text-orange-700 hover:bg-orange-50' : 'text-blue-600 hover:text-blue-700 hover:bg-blue-50'}`}
                        >
                          <Play className="w-4 h-4 mr-1" />
                          {file.status === 'failed' || file.status === 'stopped' ? '重新解析' : '解析'}
                        </Button>
                      )}

                      {/* 查看日志按钮 - 对解析中、解析失败或已停止的PDF显示，已解析的不显示 */}
                      {file.filename.toLowerCase().endsWith('.pdf') && (file.status === 'processing' || file.status === 'failed' || file.status === 'stopped') && file.doc_id && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation()
                            openLogDialog(
                              file.doc_id!, 
                              file.filename, 
                              file.status as 'pending' | 'processing' | 'parsing' | 'completed' | 'failed' | 'stopped'
                            )
                          }}
                          className="h-8 w-8 text-gray-500 hover:text-blue-600 hover:bg-blue-50"
                          title="查看解析日志"
                        >
                          <Terminal className="w-4 h-4" />
                        </Button>
                      )}

                      {/* 下载解析后的 Markdown 按钮（带图片）- 只对已解析的PDF显示 */}
                      {file.filename.toLowerCase().endsWith('.pdf') && file.status === 'completed' && file.related_files && (
                        (() => {
                          const mdFile = file.related_files.find(f => 
                            f.filename.endsWith('.md') || f.file_type === 'markdown'
                          )
                          return mdFile ? (
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={(e) => {
                                e.stopPropagation()
                                // 使用新的下载函数，下载带图片的 ZIP 包
                                const zipFilename = `${mdFile.filename.replace('.md', '')}.zip`
                                downloadMarkdownWithImages(mdFile.id, zipFilename)
                                  .catch(error => {
                                    console.error('下载失败:', error)
                                    alert('下载失败: ' + error.message)
                                  })
                              }}
                              className="h-8 w-8 text-gray-500 hover:text-purple-600 hover:bg-purple-50"
                              title={`下载 ${mdFile.filename}（含图片）`}
                            >
                              <FileType className="w-4 h-4" />
                            </Button>
                          ) : null
                        })()
                      )}

                      {/* 预览按钮 */}
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={(e) => {
                          e.stopPropagation()
                          handlePreview(file)
                        }}
                        className="h-8 w-8 text-gray-500 hover:text-green-600 hover:bg-green-50"
                        title="预览"
                      >
                        <Eye className="w-4 h-4" />
                      </Button>

                      {/* 删除按钮 */}
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteFile(file.id)
                        }}
                        className="h-8 w-8 text-gray-400 hover:text-red-500 hover:bg-red-50"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>

              {/* 分页 */}
              <Pagination
                currentPage={currentPage}
                totalPages={totalPages}
                totalItems={totalItems}
                pageSize={pageSize}
                onPageChange={handlePageChange}
                onPageSizeChange={handlePageSizeChange}
              />
            </div>
          )}
        </div>
      </div>

      {/* 预览弹窗 */}
      <PreviewDialog
        isOpen={isPreviewOpen}
        onClose={handleClosePreview}
        file={previewFile}
      />

      {/* 解析日志弹窗 */}
      <ParseLogDialog
        isOpen={logDialogState.isOpen}
        onClose={closeLogDialog}
        taskId={logDialogState.taskId}
        filename={logDialogState.filename}
        status={logDialogState.status}
        onStatusChange={handleLogDialogStatusChange}
      />

      {/* 批量上传进度弹窗 */}
      <BatchUploadDialog
        isOpen={isUploadDialogOpen}
        onClose={() => setIsUploadDialogOpen(false)}
        tasks={uploadTasks}
        onRetry={handleRetryUpload}
        onRetryAll={handleRetryAllUploads}
        onCancel={handleCancelUpload}
      />
    </div>
  )
}

export default Documents
