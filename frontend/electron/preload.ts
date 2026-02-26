/**
 * Uverse Electron 预加载脚本
 * 在渲染进程上下文中安全地暴露主进程 API
 */
import { contextBridge, ipcRenderer } from 'electron'

// 暴露给渲染进程的 API 类型定义
interface ElectronAPI {
  // 应用信息
  getAppVersion: () => Promise<string>
  getPlatform: () => Promise<string>
  
  // 后端服务
  getBackendStatus: () => Promise<{ 
    running: boolean
    pid?: number
    port?: number
    pgConfigStatus?: 'ok' | 'not_found' | 'error'
    pgConfigError?: string
    pathCheck?: {
      valid: boolean
      postgres?: { valid: boolean; error?: string }
      store?: { valid: boolean; error?: string }
      models?: { valid: boolean; error?: string }
    }
    servicesStartStatus?: 'idle' | 'starting' | 'started' | 'failed'
    servicesStartError?: string
  }>
  waitForServicesStart: () => Promise<{ status: string; error?: string; pathCheck?: any }>
  startServices: () => Promise<{ success: boolean; status: string; error?: string }>
  restartBackend: () => Promise<{ success: boolean }>
  
  // 配置管理（后端未启动时使用）
  getConfigFromEnv: () => Promise<{ success: boolean; configs?: Array<{key: string; value: string; description: string; category: string}>; message?: string }>
  saveConfigToEnv: (configs: Record<string, string>) => Promise<{ success: boolean; message?: string; pathErrors?: Record<string, string> }>
  checkPaths: (paths: Record<string, string>) => Promise<{ valid: boolean; errors: Record<string, string> }>
  
  // 前端日志
  logWrite: (level: string, message: string) => Promise<void>
  
  // 系统操作
  openExternal: (url: string) => Promise<void>
  
  // 环境信息
  isElectron: boolean
  
  // 事件监听
  onNavigateToSettings: (callback: (data: { errors: string[]; message: string }) => void) => () => void
}

const electronAPI: ElectronAPI = {
  // 应用信息
  getAppVersion: () => ipcRenderer.invoke('app:getVersion'),
  getPlatform: () => ipcRenderer.invoke('app:getPlatform'),
  
  // 后端服务
  getBackendStatus: () => ipcRenderer.invoke('backend:getStatus'),
  waitForServicesStart: () => ipcRenderer.invoke('backend:waitForStart'),
  startServices: () => ipcRenderer.invoke('services:start'),
  restartBackend: () => ipcRenderer.invoke('backend:restart'),
  
  // 配置管理（后端未启动时使用）
  getConfigFromEnv: () => ipcRenderer.invoke('config:getFromEnv'),
  saveConfigToEnv: (configs: Record<string, string>) => ipcRenderer.invoke('config:saveToEnv', configs),
  checkPaths: (paths: Record<string, string>) => ipcRenderer.invoke('config:checkPaths', paths),
  
  // 前端日志
  logWrite: (level: string, message: string) => ipcRenderer.invoke('log:write', level, message),
  
  // 系统操作
  openExternal: (url: string) => ipcRenderer.invoke('shell:openExternal', url),
  
  // 环境信息
  isElectron: true,
  
  // 事件监听
  onNavigateToSettings: (callback) => {
    const handler = (_event: any, data: { errors: string[]; message: string }) => callback(data)
    ipcRenderer.on('navigate-to-settings', handler)
    return () => ipcRenderer.removeListener('navigate-to-settings', handler)
  },
}

// 通过 contextBridge 安全地暴露 API
contextBridge.exposeInMainWorld('electronAPI', electronAPI)
