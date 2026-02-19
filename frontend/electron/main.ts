/**
 * Uverse Electron 主进程入口
 * 负责启动后端 FastAPI 服务和嵌入式 PostgreSQL
 */
import { app, BrowserWindow, ipcMain, screen, Tray, Menu, shell } from 'electron'
import * as path from 'path'
import { spawn, ChildProcess } from 'child_process'
import * as fs from 'fs'
import * as http from 'http'

// 设置应用名称为大写 Uverse（必须在其他操作之前）
// 这会影响用户数据目录: ~/Library/Application Support/Uverse
app.setName('Uverse')

/**
 * 获取用户数据目录路径
 * macOS: ~/Library/Application Support/Uverse
 * Windows: %APPDATA%/Uverse
 */
function getUserDataPath(): string {
  return app.getPath('userData')
}

/**
 * 加载 .env 文件到环境变量
 * 优先从用户数据目录加载，如果不存在则从应用包复制
 */
function loadEnvFile(): Record<string, string> {
  const envVars: Record<string, string> = {}
  
  // 用户数据目录（可写）
  const userDataPath = getUserDataPath()
  const userEnvPath = path.join(userDataPath, '.env')
  
  // 应用包内目录（只读，作为模板）
  const resourcePath = getResourcePath()
  const bundledEnvPath = path.join(resourcePath, 'backend', '.env')
  
  // 确保用户数据目录存在
  if (!fs.existsSync(userDataPath)) {
    fs.mkdirSync(userDataPath, { recursive: true })
  }
  
  // 如果用户目录没有 .env，从应用包复制一份
  if (!fs.existsSync(userEnvPath) && fs.existsSync(bundledEnvPath)) {
    try {
      fs.copyFileSync(bundledEnvPath, userEnvPath)
    } catch (err) {
      console.error('复制配置文件失败:', err)
    }
  }
  
  // 从用户目录加载配置
  if (!fs.existsSync(userEnvPath)) {
    return envVars
  }
  
  try {
    const content = fs.readFileSync(userEnvPath, 'utf-8')
    const lines = content.split('\n')
    
    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      
      const equalIndex = trimmed.indexOf('=')
      if (equalIndex === -1) continue
      
      const key = trimmed.substring(0, equalIndex).trim()
      let value = trimmed.substring(equalIndex + 1).trim()
      
      const hashIndex = value.indexOf('#')
      if (hashIndex > 0 && !value.startsWith('"') && !value.startsWith("'")) {
        value = value.substring(0, hashIndex).trim()
      }
      
      if ((value.startsWith('"') && value.endsWith('"')) ||
          (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1)
      }
      
      if (key) {
        envVars[key] = value
      }
    }
  } catch (err) {
    console.error('读取 .env 文件失败:', err)
  }
  
  return envVars
}

// 保持窗口对象的全局引用
let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let backendProcess: ChildProcess | null = null
let backendPort: number = 8000
let isQuitting = false
const isPackaged = app.isPackaged
const electronLogs: Array<{timestamp: string, level: string, message: string}> = []
let isBackendReady = false

// 发送日志到后端
function sendLogToBackend(level: string, message: string) {
  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19)
  electronLogs.push({ timestamp, level, message })
  
  if (isBackendReady && backendPort) {
    const logData = JSON.stringify({ timestamp, level, message })
    const req = http.request({
      hostname: '127.0.0.1',
      port: backendPort,
      path: '/api/logs/electron',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(logData)
      },
      timeout: 1000
    })
    req.on('error', () => {})
    req.write(logData)
    req.end()
  }
}

// 批量发送缓存日志
async function sendCachedLogsToBackend() {
  if (!backendPort || electronLogs.length === 0) return
  
  const logsToSend = [...electronLogs]
  electronLogs.length = 0
  
  for (const log of logsToSend) {
    try {
      const logData = JSON.stringify(log)
      await new Promise<void>((resolve) => {
        const req = http.request({
          hostname: '127.0.0.1',
          port: backendPort,
          path: '/api/logs/electron',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(logData)
          },
          timeout: 1000
        }, () => resolve())
        req.on('error', () => resolve())
        req.write(logData)
        req.end()
      })
    } catch {}
  }
}

// 重定向 console 到后端日志
const originalConsoleLog = console.log
const originalConsoleError = console.error
const originalConsoleWarn = console.warn

console.log = (...args: any[]) => {
  const message = args.join(' ')
  originalConsoleLog.apply(console, args)
  sendLogToBackend('INFO', message)
}

console.error = (...args: any[]) => {
  const message = args.join(' ')
  originalConsoleError.apply(console, args)
  sendLogToBackend('ERROR', message)
}

console.warn = (...args: any[]) => {
  const message = args.join(' ')
  originalConsoleWarn.apply(console, args)
  sendLogToBackend('WARNING', message)
}

// 获取应用资源目录
function getResourcePath(): string {
  if (isPackaged) {
    return process.resourcesPath
  } else {
    return path.join(__dirname, '../..')
  }
}

// 获取后端可执行文件路径
function getBackendExecutable(): { 
  executable: string; 
  args: string[];
  workingDir: string; 
  isPackaged: boolean 
} {
  const resourcePath = getResourcePath()
  const backendPath = path.join(resourcePath, 'backend')
  const platform = process.platform
  const isWin = platform === 'win32'
  
  const executableName = isWin ? 'uverse-backend.exe' : 'uverse-backend'
  const onedirExecutable = path.join(backendPath, 'uverse-backend', executableName)
  const singleExecutable = path.join(backendPath, executableName)
  
  let packagedExecutable: string | null = null
  let packagedWorkingDir: string = backendPath
  
  if (fs.existsSync(onedirExecutable)) {
    packagedExecutable = onedirExecutable
    packagedWorkingDir = path.join(backendPath, 'uverse-backend')
  } else if (fs.existsSync(singleExecutable)) {
    packagedExecutable = singleExecutable
    packagedWorkingDir = backendPath
  }
  
  if (packagedExecutable) {
    if (!isWin) {
      try {
        fs.accessSync(packagedExecutable, fs.constants.X_OK)
      } catch (e) {
        try {
          fs.chmodSync(packagedExecutable, 0o755)
        } catch {}
      }
    }
    
    return {
      executable: packagedExecutable,
      args: [],
      workingDir: packagedWorkingDir,
      isPackaged: true
    }
  }
  
  // 开发环境
  const venvPython = isWin
    ? path.join(backendPath, '.venv', 'Scripts', 'python.exe')
    : path.join(backendPath, '.venv', 'bin', 'python3')
  const pythonPath = fs.existsSync(venvPython) ? venvPython : (isWin ? 'python.exe' : 'python3')
  
  return {
    executable: pythonPath,
    args: [path.join(backendPath, 'main.py')],
    workingDir: backendPath,
    isPackaged: false
  }
}

// 检查后端健康
function checkBackendHealth(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/api/health`, (res: http.IncomingMessage) => {
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(500, () => {
      req.destroy()
      resolve(false)
    })
  })
}

// 等待后端就绪
async function waitForBackend(port: number): Promise<boolean> {
  await new Promise(resolve => setTimeout(resolve, 2000))
  
  const maxRetries = 5
  const retryInterval = 2000
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    if (await checkBackendHealth(port)) {
      return true
    }
    
    if (attempt < maxRetries) {
      await new Promise(resolve => setTimeout(resolve, retryInterval))
    }
  }
  
  const { dialog } = require('electron')
  dialog.showErrorBox(
    '服务启动失败',
    '后端服务启动超时，请检查日志获取详细信息。\n\n程序即将退出。'
  )
  
  app.quit()
  return false
}

// 启动后端服务
let backendStarting = false
let backendStarted = false

function startBackend(): Promise<boolean> {
  return new Promise((resolve, reject) => {
    if (backendStarting || backendStarted) {
      resolve(backendStarted)
      return
    }
    backendStarting = true
    
    const { executable, args, workingDir, isPackaged: backendIsPackaged } = getBackendExecutable()
    
    console.log(`启动后端: ${path.basename(executable)}`)
    
    if (!fs.existsSync(workingDir)) {
      reject(new Error('Backend directory not found'))
      return
    }
    
    const envFileVars = loadEnvFile()
    
    const env: Record<string, string | undefined> = {
      ...process.env,
      HOST: '127.0.0.1',
      PORT: String(backendPort),
      PYTHONUNBUFFERED: '1',
      PYTHONPATH: backendIsPackaged ? undefined : workingDir,
      ...envFileVars
    }
    
    const isWin = process.platform === 'win32'
    
    const spawnOptions: any = {
      cwd: workingDir,
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
      detached: false,
      shell: false
    }
    
    if (isWin) {
      spawnOptions.windowsHide = true
    }
    
    backendProcess = spawn(executable, args, spawnOptions)
    
    if (!backendProcess) {
      reject(new Error('Failed to create backend process'))
      return
    }
    
    let processExited = false
    let exitCode: number | null = null
    
    backendProcess.stdout?.on('data', (data: Buffer) => {
      const output = data.toString().trim()
      if (output) console.log(output)
    })
    
    backendProcess.stderr?.on('data', (data: Buffer) => {
      const output = data.toString().trim()
      if (!output) return
      if (output.includes('INFO:') || output.includes('WARNING:')) {
        console.log(output)
      } else {
        console.error(output)
      }
    })
    
    backendProcess.on('close', (code: number) => {
      processExited = true
      exitCode = code
      backendProcess = null
      backendStarting = false
      backendStarted = false
      isBackendReady = false
    })
    
    backendProcess.on('error', (err: Error) => {
      reject(err)
    })
    
    setTimeout(() => {
      if (processExited) {
        reject(new Error(`Backend process exited immediately with code ${exitCode}`))
        return
      }
    }, 1000)
    
    waitForBackend(backendPort).then(async (isReady) => {
      if (processExited && !isReady) {
        return
      }
      
      if (isReady) {
        isBackendReady = true
        backendStarted = true
        backendStarting = false
        await sendCachedLogsToBackend()
        resolve(true)
      }
    })
  })
}

// 停止后端服务
function stopBackend() {
  return new Promise<void>((resolve) => {
    if (!backendProcess) {
      resolve()
      return
    }
    
    const pid = backendProcess.pid
    if (!pid) {
      backendProcess = null
      resolve()
      return
    }
    
    backendProcess.once('close', () => {
      backendProcess = null
      resolve()
    })
    
    if (process.platform === 'win32') {
      const { exec } = require('child_process')
      exec(`taskkill /pid ${pid} /T /F`, (err: any) => {
        if (err) backendProcess?.kill('SIGKILL')
      })
    } else {
      try {
        backendProcess.kill('SIGTERM')
      } catch (e) {}
    }
    
    setTimeout(() => {
      if (backendProcess) {
        try {
          backendProcess.kill('SIGKILL')
        } catch (e) {}
        backendProcess = null
        resolve()
      }
    }, 8000)
  })
}

// 创建主窗口
function createWindow(): void {
  const primaryDisplay = screen.getPrimaryDisplay()
  const { width, height } = primaryDisplay.workAreaSize
  
  mainWindow = new BrowserWindow({
    width: width,
    height: height,
    x: 0,
    y: 0,
    minWidth: 800,
    minHeight: 600,
    title: 'Uverse',
    maximizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs'),
      webSecurity: false,
    },
    show: false,
  })
  
  if (isPackaged) {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  } else {
    const devServerUrl = 'http://localhost:5173'
    const req = http.get(devServerUrl, (res: http.IncomingMessage) => {
      if (res.statusCode === 200) {
        mainWindow?.loadURL(devServerUrl)
      } else {
        mainWindow?.loadFile(path.join(__dirname, '../dist/index.html'))
      }
    })
    req.on('error', () => {
      mainWindow?.loadFile(path.join(__dirname, '../dist/index.html'))
    })
    req.setTimeout(3000, () => {
      req.destroy()
      mainWindow?.loadFile(path.join(__dirname, '../dist/index.html'))
    })
  }
  
  mainWindow.webContents.session.setProxy({
    proxyRules: 'direct://',
    proxyBypassRules: 'localhost,127.0.0.1,::1,<local>'
  }).catch(() => {})
  
  mainWindow.once('ready-to-show', () => {
    if (mainWindow) {
      mainWindow.show()
      mainWindow.focus()
    }
  })
  
  mainWindow.on('close', async (e) => {
    if (!isQuitting) {
      isQuitting = true
      e.preventDefault()
      await stopBackend()
      mainWindow?.destroy()
    }
  })
  
  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// 创建托盘图标
function createTray(): void {
  let iconPath: string
  if (isPackaged) {
    iconPath = path.join(process.resourcesPath, 'icon.png')
  } else {
    iconPath = path.join(__dirname, '../build/icon.png')
  }
  
  if (!fs.existsSync(iconPath)) {
    const altIconPath = path.join(__dirname, '../../build/icon.png')
    if (fs.existsSync(altIconPath)) {
      iconPath = altIconPath
    } else {
      return
    }
  }
  
  try {
    tray = new Tray(iconPath)
    tray.setToolTip('Uverse')
    
    const contextMenu = Menu.buildFromTemplate([
      {
        label: '显示 Uverse',
        click: () => {
          if (mainWindow) {
            mainWindow.show()
            mainWindow.focus()
          } else {
            createWindow()
          }
        }
      },
      {
        label: '退出',
        click: () => {
          isQuitting = true
          app.quit()
        }
      }
    ])
    
    tray.setContextMenu(contextMenu)
    
    tray.on('click', () => {
      if (mainWindow) {
        if (mainWindow.isVisible()) {
          mainWindow.hide()
        } else {
          mainWindow.show()
          mainWindow.focus()
        }
      } else {
        createWindow()
      }
    })
  } catch {}
}

// Electron 初始化
const appStartTime = Date.now()

app.whenReady().then(async () => {
  try {
    const readyTime = Date.now() - appStartTime
    console.log(`Uverse 启动中 (${isPackaged ? '生产' : '开发'}模式, ${readyTime}ms)`)
    
    createWindow()
    
    startBackend().catch((error) => {
      console.error('启动后端失败:', error)
    })
    
    createTray()
  } catch (error) {
    console.error('启动失败:', error)
    createWindow()
    createTray()
  }
})

app.on('window-all-closed', async () => {
  await stopBackend()
  app.quit()
})

app.on('activate', () => {
  if (mainWindow === null && !isQuitting) {
    createWindow()
  }
})

app.on('before-quit', async (e) => {
  if (!isQuitting) {
    isQuitting = true
    e.preventDefault()
    await stopBackend()
    app.quit()
  }
})

// IPC 通信
ipcMain.handle('app:getVersion', () => app.getVersion())
ipcMain.handle('app:getPlatform', () => process.platform)
ipcMain.handle('backend:getStatus', async () => ({
  running: await checkBackendHealth(backendPort),
  pid: backendProcess?.pid,
  port: backendPort
}))
ipcMain.handle('backend:restart', async () => {
  stopBackend()
  await new Promise(resolve => setTimeout(resolve, 1000))
  const success = await startBackend()
  return { success }
})
ipcMain.handle('shell:openExternal', async (_, url: string) => {
  await shell.openExternal(url)
})
