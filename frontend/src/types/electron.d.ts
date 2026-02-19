/**
 * Electron API 类型声明
 */

export interface ElectronAPI {
  // 应用信息
  getAppVersion: () => Promise<string>
  getPlatform: () => Promise<string>
  
  // 后端服务
  getBackendStatus: () => Promise<{ running: boolean; pid?: number }>
  restartBackend: () => Promise<{ success: boolean }>
  
  // 环境信息
  isElectron: boolean
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}

export {}
