"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Uverse Electron 预加载脚本
 * 在渲染进程上下文中安全地暴露主进程 API
 */
const electron_1 = require("electron");
const electronAPI = {
    // 应用信息
    getAppVersion: () => electron_1.ipcRenderer.invoke('app:getVersion'),
    getPlatform: () => electron_1.ipcRenderer.invoke('app:getPlatform'),
    // 后端服务
    getBackendStatus: () => electron_1.ipcRenderer.invoke('backend:getStatus'),
    restartBackend: () => electron_1.ipcRenderer.invoke('backend:restart'),
    // 系统操作
    openExternal: (url) => electron_1.ipcRenderer.invoke('shell:openExternal', url),
    // 环境信息
    isElectron: true,
};
// 通过 contextBridge 安全地暴露 API
electron_1.contextBridge.exposeInMainWorld('electronAPI', electronAPI);
//# sourceMappingURL=preload.js.map