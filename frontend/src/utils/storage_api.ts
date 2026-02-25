import { API_BASE_URL } from './api'

// 日志条目类型
export interface LogEntry {
  timestamp: string
  level: string
  message: string
}

// 上传文档（带超时控制）
export async function uploadDocument(
  file: File,
  options?: {
    onProgress?: (progress: number) => void
    timeout?: number
  }
): Promise<{
  filename: string
  doc_id: string
  file_id: string
  status: string
  size: number
  bucket: string
  object_key: string
  s3_url: string
  message?: string
  file_type?: string
  needs_parse?: boolean
}> {
  const url = `${API_BASE_URL}/documents/upload`
  console.log(`[uploadDocument] 开始上传: ${file.name}, 大小: ${file.size}, type=${file.type}`)
  
  // 检测文件是否可读（处理 OneDrive 等云存储的"按需同步"文件）
  // 这些文件虽然 File 对象存在，但内容可能需要从云端下载
  console.log('[uploadDocument] 检测文件可读性...')
  try {
    // 尝试读取前 1KB 数据，设置 3 秒超时
    const testChunk = file.slice(0, Math.min(1024, file.size))
    const testReader = new FileReader()
    
    await Promise.race([
      new Promise<void>((resolve, reject) => {
        testReader.onload = () => resolve()
        testReader.onerror = () => reject(new Error('文件读取失败'))
        testReader.readAsArrayBuffer(testChunk)
      }),
      new Promise<never>((_, reject) => 
        setTimeout(() => reject(new Error('文件读取超时')), 3000)
      )
    ])
    
    console.log('[uploadDocument] 文件可读性检测通过')
  } catch (e) {
    console.error('[uploadDocument] 文件可读性检测失败:', e)
    throw new Error('无法读取文件，该文件可能存储在云端，请先将文件复制到本地文件夹，或等待文件同步完成后再上传。')
  }
  
  // 使用 XMLHttpRequest 替代 fetch，Electron 环境下更稳定
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const timeout = options?.timeout || 120000 // 默认 120 秒超时
    
    // 设置超时
    xhr.timeout = timeout
    
    // 进度监听
    xhr.upload.addEventListener('progress', (e) => {
      console.log(`[uploadDocument] 上传进度: ${e.loaded}/${e.total}`)
      if (e.lengthComputable && options?.onProgress) {
        const progress = Math.round((e.loaded / e.total) * 100)
        options.onProgress(progress)
      }
    })
    
    xhr.addEventListener('loadstart', () => {
      console.log('[uploadDocument] 请求开始发送')
    })
    
    xhr.addEventListener('load', () => {
      console.log(`[uploadDocument] 请求完成, 状态: ${xhr.status}`)
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText)
          resolve(response)
        } catch (e) {
          reject(new Error('解析响应失败'))
        }
      } else {
        let errorMessage = '上传失败'
        try {
          const error = JSON.parse(xhr.responseText)
          errorMessage = error.detail || error.message || '上传失败'
        } catch {
          errorMessage = `上传失败: ${xhr.status} ${xhr.statusText}`
        }
        reject(new Error(errorMessage))
      }
    })
    
    xhr.addEventListener('error', (e) => {
      console.error('[uploadDocument] 请求错误:', e)
      reject(new Error('上传请求失败，请检查网络连接'))
    })
    
    xhr.addEventListener('timeout', () => {
      console.error('[uploadDocument] 请求超时')
      reject(new Error('上传超时，请检查网络连接或尝试上传较小的文件'))
    })
    
    xhr.addEventListener('abort', () => {
      console.log('[uploadDocument] 请求被取消')
      reject(new Error('上传已取消'))
    })
    
    // 创建 FormData，直接使用 File 对象
    // 通过前面的检测，我们已经确认文件是可读的
    const formData = new FormData()
    formData.append('file', file, file.name)
    
    // 发送请求
    console.log(`[uploadDocument] 发送 POST 请求到: ${url}`)
    xhr.open('POST', url)
    xhr.send(formData)
    console.log('[uploadDocument] xhr.send() 已调用')
  })
}

// 开始解析 PDF
export async function startParse(docId: string, filename: string) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 120000) // 2分钟超时（MinerU 初始化可能需要较长时间）

  try {
    const response = await fetch(
      `${API_BASE_URL}/documents/parse/${docId}?filename=${encodeURIComponent(filename)}`,
      {
        method: 'POST',
        signal: controller.signal,
      }
    )

    clearTimeout(timeoutId)

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || '启动解析失败')
    }

    return response.json()
  } catch (error) {
    clearTimeout(timeoutId)
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('启动解析超时，请稍后查看状态')
    }
    throw error
  }
}

// 获取解析状态
export async function getParseStatus(taskId: string) {
  const response = await fetch(`${API_BASE_URL}/documents/parse/status/${taskId}`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取状态失败')
  }

  return response.json()
}

// 停止解析任务
export async function stopParse(taskId: string): Promise<{ task_id: string; status: string; message: string }> {
  const response = await fetch(`${API_BASE_URL}/documents/parse/stop/${taskId}`, {
    method: 'POST',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '停止解析失败')
  }

  return response.json()
}

// 获取解析结果
export async function getParseResult(taskId: string) {
  const response = await fetch(`${API_BASE_URL}/documents/parse/result/${taskId}`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取结果失败')
  }

  return response.json()
}

// 删除文档
export async function deleteDocument(docId: string) {
  const response = await fetch(`${API_BASE_URL}/documents/${docId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '删除失败')
  }

  return response.json()
}

// 文件列表响应类型
export interface FileListResponse {
  files: Array<{
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
  }>
  total: number
  page: number
  page_size: number
  total_pages: number
}

// ==================== 文件管理 API ====================

// 获取所有文件列表（支持分页）
export async function listFiles(fileType?: string, page: number = 1, pageSize: number = 20): Promise<FileListResponse> {
  let url = `${API_BASE_URL}/documents/files?page=${page}&page_size=${pageSize}`
  if (fileType) {
    url += `&file_type=${fileType}`
  }

  const response = await fetch(url)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取文件列表失败')
  }

  return response.json()
}

// 获取文件详情
export async function getFileDetail(fileId: string) {
  const response = await fetch(`${API_BASE_URL}/documents/files/${fileId}`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取文件详情失败')
  }

  return response.json()
}

// 获取文件内容
export async function getFileContent(fileId: string) {
  const response = await fetch(`${API_BASE_URL}/documents/files/${fileId}/content`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取文件内容失败')
  }

  return response.json()
}

// 更新 Markdown 文件内容
export async function updateFileContent(fileId: string, content: string) {
  const response = await fetch(`${API_BASE_URL}/documents/files/${fileId}/content`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ content }),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '保存文件失败')
  }

  return response.json()
}

// 删除文件
export async function deleteFile(fileId: string) {
  const response = await fetch(`${API_BASE_URL}/documents/files/${fileId}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '删除文件失败')
  }

  return response.json()
}

// 下载 Markdown 文件及其图片（打包成 ZIP）
export async function downloadMarkdownWithImages(fileId: string, filename: string) {
  const response = await fetch(`${API_BASE_URL}/documents/files/${fileId}/download-with-images`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '下载失败')
  }

  // 获取 blob 数据
  const blob = await response.blob()
  
  // 创建下载链接
  const downloadUrl = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  
  // 清理
  document.body.removeChild(link)
  window.URL.revokeObjectURL(downloadUrl)
}

// ==================== 解析日志 API ====================

// 获取解析日志（轮询使用）
export interface ParseLogsResponse {
  task_id: string
  logs: LogEntry[]
  total: number      // 总日志数
  returned: number   // 返回的日志数
  offset: number     // 跳过的日志数
  has_more: boolean  // 是否还有更多日志
}

export async function getParseLogs(taskId: string, limit: number = 5000, offset: number = 0): Promise<ParseLogsResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/parse/logs/${taskId}?limit=${limit}&offset=${offset}`)

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '获取日志失败')
  }

  return response.json()
}
