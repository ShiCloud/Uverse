import axios from 'axios'

// API 基础 URL - Electron 应用中直接访问后端服务
export const API_BASE_URL = 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,  // 10秒超时，给后端启动足够时间
})

// 健康检查
export const checkHealth = async () => {
  const response = await api.get('/health')
  return response.data
}

// 服务就绪检查（静默模式，避免控制台报错）
export const checkReady = async () => {
  try {
    const response = await api.get('/ready', {
      // 使用单独的配置，避免触发全局错误处理
      validateStatus: (status) => status < 500,
    })
    return response.data
  } catch (error: any) {
    // 连接被拒绝是预期的，静默返回
    if (error.code === 'ECONNREFUSED' || error.message?.includes('Network Error')) {
      return { status: 'starting', services: {} }
    }
    throw error
  }
}

// 等待服务就绪（带重试）
export const waitForReady = async (
  options: {
    maxRetries?: number
    retryDelay?: number
    initialDelay?: number
    onChecking?: (attempt: number) => void
    onStatus?: (status: 'checking' | 'starting' | 'ready' | 'error', message?: string) => void
  } = {}
): Promise<{ ready: boolean; data?: any; error?: string }> => {
  const { maxRetries = 10, retryDelay = 3000, initialDelay = 3000, onChecking, onStatus } = options
  
  onStatus?.('checking', '正在检查服务状态...')
  
  // 初始延迟，给后端服务启动时间，避免立即报错
  if (initialDelay > 0) {
    await new Promise(resolve => setTimeout(resolve, initialDelay))
  }
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      onChecking?.(attempt)
      const response = await api.get('/ready', {
        // 静默请求，避免在控制台显示网络错误
        validateStatus: () => true,
      })
      
      if (response.status === 200 && response.data.status === 'ready') {
        onStatus?.('ready', '所有服务已就绪')
        return { ready: true, data: response.data }
      }
      
      // 如果是 503，说明服务还在启动中（这是正常的）
      if (response.status === 503) {
        const services = response.data?.services || {}
        const startingServices = Object.entries(services)
          .filter(([_, info]: [string, any]) => info?.status !== 'ok')
          .map(([name, _]) => name === 'database' ? '数据库' : name === 'rustfs' ? '存储服务' : name)
        
        onStatus?.('starting', `正在启动: ${startingServices.join(', ')}...`)
        
        if (attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, retryDelay))
          continue
        }
      }
    } catch (error: any) {
      // 连接被拒绝或网络错误是预期的（服务正在启动），静默重试
      const isConnectionError = error.code === 'ECONNREFUSED' || 
                                error.message?.includes('Network Error') ||
                                error.message?.includes('connection refused')
      
      if (isConnectionError && attempt < maxRetries) {
        onStatus?.('starting', `等待服务启动 (${attempt}/${maxRetries})...`)
        await new Promise(resolve => setTimeout(resolve, retryDelay))
        continue
      }
      
      // 其他错误或达到最大重试次数
      if (attempt >= maxRetries) {
        const errorMsg = error.response?.data?.message || error.message || '服务启动超时'
        onStatus?.('error', errorMsg)
        console.log(`[waitForReady] 最终错误: ${errorMsg}`)
        return {
          ready: false,
          error: errorMsg
        }
      }
      
      // 其他错误，继续重试
      onStatus?.('starting', `连接失败，正在重试 (${attempt}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, retryDelay))
    }
  }
  
  onStatus?.('error', '服务启动超时')
  return { ready: false, error: '服务启动超时' }
}

// 发送聊天消息
export const sendMessage = async (message: string) => {
  const response = await api.post('/chat/', { message })
  return response.data
}

// 上传文档
export const uploadDocument = async (file: File) => {
  const formData = new FormData()
  formData.append('file', file)
  
  const response = await api.post('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return response.data
}

// 获取文档列表
export const getDocuments = async () => {
  const response = await api.get('/documents/')
  return response.data
}

// 获取文档列表（新接口）
export const listDocuments = async () => {
  const response = await api.get('/documents/')
  return response.data.documents || []
}

// 开始解析 PDF
export const startParse = async (docId: string, filename: string) => {
  const response = await api.post(`/documents/parse/${docId}?filename=${encodeURIComponent(filename)}`)
  return response.data
}

// 获取解析状态
export const getParseStatus = async (taskId: string) => {
  const response = await api.get(`/documents/parse/status/${taskId}`)
  return response.data
}

// 获取解析结果
export const getParseResult = async (taskId: string) => {
  const response = await api.get(`/documents/parse/result/${taskId}`)
  return response.data
}

// 删除文档
export const deleteDocument = async (docId: string) => {
  const response = await api.delete(`/documents/${docId}`)
  return response.data
}

// 获取配置列表 - 返回原始响应格式
export const getConfigs = async () => {
  const response = await api.get('/config')
  return response.data
}

// 获取配置键值对 - 返回对象格式 {key: value}
export const getConfigValues = async (): Promise<Record<string, string>> => {
  const response = await api.get('/config')
  const data = response.data
  
  // 将 configs 数组转换为对象格式
  const configMap: Record<string, string> = {}
  if (data.configs && Array.isArray(data.configs)) {
    data.configs.forEach((item: {key: string, value: string}) => {
      configMap[item.key] = item.value
    })
  }
  
  return configMap
}

// 更新配置
export const updateConfigs = async (configs: Record<string, string>) => {
  const response = await api.post('/config', { configs })
  return response.data
}

// 检查路径是否存在
export const checkPaths = async (paths: Record<string, string>) => {
  const response = await api.post('/config/check-paths', { paths })
  return response.data
}

// 关闭应用程序
export const shutdownApp = async () => {
  const response = await api.post('/shutdown')
  return response.data
}

// 获取配置分类
export const getConfigCategories = async () => {
  const response = await api.get('/config/categories')
  return response.data
}

// 获取日志
export const getLogs = async (params?: { date?: string; limit?: number; offset?: number; level?: string }) => {
  const response = await api.get('/logs', { params })
  return response.data
}

// 获取可用日志日期
export const getLogDates = async () => {
  const response = await api.get('/logs/dates')
  return response.data
}

// 获取日志级别
export const getLogLevels = async () => {
  const response = await api.get('/logs/levels')
  return response.data
}

// 清空日志
export const clearLogs = async () => {
  const response = await api.post('/logs/clear')
  return response.data
}

// 检查数据库状态
export const getDbStatus = async () => {
  const response = await api.get('/config/db-status')
  return response.data as {
    available: boolean
    mode: 'embedded' | 'external'
    error?: string
  }
}

// 测试外部数据库连接
export const testDbConnection = async (params: {
  host: string
  port: string
  user: string
  password: string
  database: string
}) => {
  const response = await api.post('/config/test-db-connection', params)
  return response.data as {
    success: boolean
    message: string
  }
}

export default api
