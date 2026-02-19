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
  getBackendStatus: () => Promise<{ running: boolean; pid?: number; port?: number }>
  restartBackend: () => Promise<{ success: boolean }>
  
  // 系统操作
  openExternal: (url: string) => Promise<void>
  
  // 环境信息
  isElectron: boolean
}

const electronAPI: ElectronAPI = {
  // 应用信息
  getAppVersion: () => ipcRenderer.invoke('app:getVersion'),
  getPlatform: () => ipcRenderer.invoke('app:getPlatform'),
  
  // 后端服务
  getBackendStatus: () => ipcRenderer.invoke('backend:getStatus'),
  restartBackend: () => ipcRenderer.invoke('backend:restart'),
  
  // 系统操作
  openExternal: (url: string) => ipcRenderer.invoke('shell:openExternal', url),
  
  // 环境信息
  isElectron: true,
}

// 通过 contextBridge 安全地暴露 API
contextBridge.exposeInMainWorld('electronAPI', electronAPI)
