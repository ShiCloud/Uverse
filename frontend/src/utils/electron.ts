/**
 * Electron 工具函数
 * 提供与 Electron 主进程通信的便捷方法
 */

// 检查是否在 Electron 环境中
export const isElectron = (): boolean => {
  return typeof window !== 'undefined' && window.electronAPI !== undefined
}

// 获取应用版本
export const getAppVersion = async (): Promise<string> => {
  if (isElectron()) {
    return window.electronAPI.getAppVersion()
  }
  return '0.0.0'
}

// 获取平台信息
export const getPlatform = async (): Promise<string> => {
  if (isElectron()) {
    return window.electronAPI.getPlatform()
  }
  return 'web'
}

// 获取后端服务状态
export const getBackendStatus = async (): Promise<{ running: boolean; pid?: number }> => {
  if (isElectron()) {
    return window.electronAPI.getBackendStatus()
  }
  return { running: false }
}

// 重启后端服务
export const restartBackend = async (): Promise<{ success: boolean }> => {
  if (isElectron()) {
    return window.electronAPI.restartBackend()
  }
  return { success: false }
}
