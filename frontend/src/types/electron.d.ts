/**
 * Electron API 类型声明
 */

export interface PathCheckResult {
  valid: boolean
  postgres?: { valid: boolean; error?: string }
  store?: { valid: boolean; error?: string }
  models?: { valid: boolean; error?: string }
}

export interface BackendStatus {
  running: boolean
  pid?: number
  pgConfigStatus?: 'ok' | 'not_found' | 'error'
  pgConfigError?: string
  pathCheck?: PathCheckResult
  servicesStartStatus?: 'idle' | 'starting' | 'started' | 'failed'
  servicesStartError?: string
}

export interface ConfigItem {
  key: string
  value: string
  description: string
  category: string
}

export interface ElectronAPI {
  // 应用信息
  getAppVersion: () => Promise<string>
  getPlatform: () => Promise<string>
  
  // 后端服务
  getBackendStatus: () => Promise<BackendStatus>
  waitForServicesStart: () => Promise<{ status: string; error?: string; pathCheck?: PathCheckResult }>
  restartBackend: () => Promise<{ success: boolean }>
  
  // 配置管理（后端未启动时使用）
  getConfigFromEnv: () => Promise<{ 
    success: boolean
    configs?: ConfigItem[]
    message?: string 
  }>
  saveConfigToEnv: (configs: Record<string, string>) => Promise<{ 
    success: boolean
    message?: string 
    pathErrors?: Record<string, string>
  }>
  
  // 前端日志
  logWrite: (level: string, message: string) => Promise<void>
  
  // 系统操作
  openExternal: (url: string) => Promise<void>
  
  // 环境信息
  isElectron: boolean
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}

export {}
