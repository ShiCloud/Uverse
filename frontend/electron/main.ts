/**
 * Uverse Electron 主进�?- Windows 专用
 * �?backend/.env 读取配置，统一管理 PostgreSQL、RustFS、Python 后端生命周期
 */
import { app, BrowserWindow, ipcMain, screen, Tray, Menu } from 'electron'
import * as path from 'path'
import { spawn, ChildProcess, execSync } from 'child_process'
import * as fs from 'fs'
import * as http from 'http'

// ==================== 控制台编码设�?====================
// Windows 控制台默认使�?GBK 编码，设置为 UTF-8 以正确显示中�?
if (process.platform === 'win32') {
  try {
    execSync('chcp 65001', { windowsHide: true, stdio: 'ignore' })
  } catch {}
}
// 设置 Node.js 默认编码
process.env.LANG = 'zh_CN.UTF-8'
process.env.LC_ALL = 'zh_CN.UTF-8'

// ==================== 日志系统 ====================
// 日志目录：程序目录下的 logs 文件夹
let LOG_DIR = ''
let LOG_INIT_ERROR = ''

// 初始化日志目录（在 app ready 后调用）
function initLogDir(): void {
  const isPackaged = app.isPackaged
  const resourcesPath = process.resourcesPath
  
  console.log('[Electron] initLogDir - isPackaged:', isPackaged)
  console.log('[Electron] initLogDir - resourcesPath:', resourcesPath)
  
  // 首先尝试使用 exe 所在目录（打包后更可靠）
  if (isPackaged) {
    try {
      const exePath = app.getPath('exe')
      const exeDir = path.dirname(exePath)
      LOG_DIR = path.join(exeDir, 'logs')
      
      console.log('[Electron] Trying exe dir:', LOG_DIR)
      
      if (!fs.existsSync(LOG_DIR)) {
        fs.mkdirSync(LOG_DIR, { recursive: true })
      }
      
      // 测试写入权限
      const testFile = path.join(LOG_DIR, '.write-test')
      fs.writeFileSync(testFile, '', 'utf-8')
      fs.unlinkSync(testFile)
      
      console.log('[Electron] Log dir initialized:', LOG_DIR)
      return
    } catch (e: any) {
      console.log('[Electron] Failed to use exe dir:', e.message)
      LOG_INIT_ERROR = `exe dir failed: ${e.message}`
    }
  }
  
  // 尝试使用 resources/app 目录
  try {
    const appRoot = isPackaged 
      ? path.join(resourcesPath, 'app')
      : path.join(__dirname, '..')
    
    LOG_DIR = path.join(appRoot, 'logs')
    console.log('[Electron] Trying app root:', LOG_DIR)
    
    if (!fs.existsSync(LOG_DIR)) {
      fs.mkdirSync(LOG_DIR, { recursive: true })
    }
    
    console.log('[Electron] Log dir initialized:', LOG_DIR)
    return
  } catch (e: any) {
    console.log('[Electron] Failed to use app root:', e.message)
    LOG_INIT_ERROR += `; app root failed: ${e.message}`
  }
  
  // 降级到 userData
  try {
    const userData = app.getPath('userData')
    LOG_DIR = path.join(userData, 'logs')
    console.log('[Electron] Trying userData:', LOG_DIR)
    
    if (!fs.existsSync(LOG_DIR)) {
      fs.mkdirSync(LOG_DIR, { recursive: true })
    }
    
    console.log('[Electron] Log dir initialized (userData):', LOG_DIR)
    return
  } catch (e: any) {
    console.error('[Electron] Failed to use userData:', e.message)
    LOG_INIT_ERROR += `; userData failed: ${e.message}`
    LOG_DIR = ''
  }
  
  console.error('[Electron] All log dir attempts failed:', LOG_INIT_ERROR)
}

// 获取当前日期作为日志文件名
function getLogFileName(): string {
  const now = new Date()
  const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
  return path.join(LOG_DIR, `electron-${dateStr}.log`)
}

// 获取带时间戳的日志前缀
function getLogPrefix(level: string): string {
  const now = new Date()
  const timeStr = `${String(now.getFullYear())}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
  return `[${timeStr}] [${level}]`
}

// 写入日志到文件
function writeLogToFile(level: string, msg: string): void {
  if (!LOG_DIR) {
    console.log('[Electron] LOG_DIR not set, skipping file log')
    return
  }
  try {
    const logFile = getLogFileName()
    const line = `${getLogPrefix(level)} ${msg}\n`
    fs.appendFileSync(logFile, line, 'utf-8')
  } catch (e: any) {
    console.error('[Electron] Failed to write log:', e.message)
  }
}

// 安全的日志输出函数（同时输出到控制台和文件）
function safeLog(...args: any[]): void {
  const msg = args.map(arg => 
    typeof arg === 'string' ? arg : String(arg)
  ).join(' ')
  // 控制台输出（使用 console.log 确保在 Electron 开发者工具中可见）
  console.log(msg)
  // 文件输出
  writeLogToFile('INFO', msg)
}
function safeError(...args: any[]): void {
  const msg = args.map(arg => 
    typeof arg === 'string' ? arg : String(arg)
  ).join(' ')
  // 控制台输出
  console.error(msg)
  // 文件输出
  writeLogToFile('ERROR', msg)
}

// ==================== 配置管理 ====================
interface AppConfig {
  // 端口配置
  backendPort: number
  pgPort: number
  rustfsPort: number
  rustfsConsolePort: number
  
  // 数据库配�?
  dbHost: string
  dbUser: string
  dbPassword: string
  dbName: string
  
  // 路径配置
  postgresDir: string
  storeDir: string
  modelsDir: string
  tempDir: string
  
  // 其他
  debug: boolean
  logLevel: string
}

let config: AppConfig = {
  backendPort: 8000,
  pgPort: 15432,
  rustfsPort: 9000,
  rustfsConsolePort: 9001,
  dbHost: '127.0.0.1',
  dbUser: 'postgres',
  dbPassword: 'postgres',
  dbName: 'postgres',
  postgresDir: '',
  storeDir: '',
  modelsDir: '',
  tempDir: '',
  debug: false,
  logLevel: 'INFO'
}

function loadEnvConfig(): void {
  const resourcePath = app.isPackaged ? process.resourcesPath : path.join(__dirname, '../..')
  const envPath = path.join(resourcePath, 'backend', '.env')
  
  if (!fs.existsSync(envPath)) {
    safeLog('[Electron] .env not found, using defaults')
    return
  }
  
  safeLog('[Electron] Loading config from:', envPath)
  
  try {
    const content = fs.readFileSync(envPath, 'utf-8')
    const env: Record<string, string> = {}
    
    for (const line of content.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      
      const eqIndex = trimmed.indexOf('=')
      if (eqIndex === -1) continue
      
      const key = trimmed.substring(0, eqIndex).trim()
      let value = trimmed.substring(eqIndex + 1).trim()
      
      // 移除引号
      if ((value.startsWith('"') && value.endsWith('"')) ||
          (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1)
      }
      
      env[key] = value
    }
    
    // 解析配置
    config.backendPort = parseInt(env['PORT'] || '8000', 10)
    config.pgPort = parseInt(env['DATABASE_PORT'] || '15432', 10)
    config.rustfsPort = 9000  // RustFS 默认端口
    config.rustfsConsolePort = 9001
    
    config.dbHost = env['DATABASE_HOST'] || '127.0.0.1'
    config.dbUser = env['DATABASE_USER'] || 'postgres'
    config.dbPassword = env['DATABASE_PASSWORD'] || 'postgres'
    config.dbName = env['DATABASE_NAME'] || 'postgres'
    
    config.postgresDir = env['POSTGRES_DIR'] || ''
    config.storeDir = env['STORE_DIR'] || ''
    config.modelsDir = env['MODELS_DIR'] || ''
    config.tempDir = env['TEMP_DIR'] || ''
    
    config.debug = (env['DEBUG'] || 'false').toLowerCase() === 'true'
    config.logLevel = env['LOG_LEVEL'] || 'INFO'
    
    safeLog('[Electron] Config loaded:', {
      backendPort: config.backendPort,
      pgPort: config.pgPort,
      dbHost: config.dbHost,
      postgresDir: config.postgresDir || '(default)',
      storeDir: config.storeDir || '(default)'
    })
  } catch (e) {
    safeError('[Electron] Failed to load .env:', e)
  }
}

function resolveConfigPaths(): void {
  const resourcePath = app.isPackaged ? process.resourcesPath : path.join(__dirname, '../..')
  const backendPath = path.join(resourcePath, 'backend')
  
  // 如果没有配置路径，使用默认�?
  if (!config.postgresDir) {
    config.postgresDir = path.join(backendPath, 'postgres')
  } else if (!path.isAbsolute(config.postgresDir)) {
    config.postgresDir = path.resolve(backendPath, config.postgresDir)
  }
  
  if (!config.storeDir) {
    config.storeDir = path.join(backendPath, 'store')
  } else if (!path.isAbsolute(config.storeDir)) {
    config.storeDir = path.resolve(backendPath, config.storeDir)
  }
  
  if (!config.modelsDir) {
    config.modelsDir = path.join(backendPath, 'models')
  } else if (!path.isAbsolute(config.modelsDir)) {
    config.modelsDir = path.resolve(backendPath, config.modelsDir)
  }
}

// ==================== 全局状�?====================
let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let pgProcess: ChildProcess | null = null
let rustfsProcess: ChildProcess | null = null
let backendProcess: ChildProcess | null = null
let isQuitting = false

// ==================== 服务停止 ====================
function stopPostgres(force = false): void {
  safeLog('[Electron] Stopping PostgreSQL...')
  const pgCtl = path.join(config.postgresDir, 'bin', 'pg_ctl.exe')
  const dataDir = path.join(config.postgresDir, 'data')
  
  // 正常关闭：先尝试 pg_ctl 优雅关闭
  if (!force && fs.existsSync(pgCtl) && fs.existsSync(dataDir)) {
    try {
      execSync(`"${pgCtl}" stop -D "${dataDir}" -m fast`, { 
        cwd: path.dirname(pgCtl),
        windowsHide: true, 
        timeout: 10000,
        stdio: 'ignore'
      })
      safeLog('[Electron] PostgreSQL stopped via pg_ctl')
      // 等待确认进程已终止
      for (let i = 0; i < 50; i++) {
        try {
          execSync('tasklist /FI "IMAGENAME eq postgres.exe" /NH | find /I "postgres"', { 
            windowsHide: true, 
            stdio: 'ignore',
            timeout: 500
          })
          // 进程还存在，等待
          execSync('timeout /T 1 /NOBREAK >nul', { windowsHide: true, stdio: 'ignore' })
        } catch {
          // 进程已不存在
          safeLog('[Electron] PostgreSQL confirmed stopped')
          return
        }
      }
      safeLog('[Electron] PostgreSQL still running after graceful stop, forcing...')
    } catch {}
  }
  
  // 强制关闭：使用 taskkill
  try {
    execSync('taskkill /F /IM postgres.exe', { windowsHide: true, timeout: 10000, stdio: 'ignore' })
    safeLog('[Electron] PostgreSQL stopped via taskkill')
    // 再等待一下确保进程已结束
    execSync('timeout /T 1 /NOBREAK >nul', { windowsHide: true, stdio: 'ignore' })
  } catch {}
}

function stopRustfs(): void {
  safeLog('[Electron] Stopping RustFS...')
  
  if (rustfsProcess?.pid) {
    try {
      execSync(`taskkill /PID ${rustfsProcess.pid} /T /F`, { windowsHide: true, timeout: 5000, stdio: 'ignore' })
      safeLog('[Electron] RustFS stopped via PID')
      rustfsProcess = null
      return
    } catch {}
  }
  
  try {
    execSync('taskkill /F /IM rustfs.exe', { windowsHide: true, timeout: 3000, stdio: 'ignore' })
    safeLog('[Electron] RustFS stopped via taskkill')
  } catch {}
  rustfsProcess = null
}

function stopBackend(): void {
  safeLog('[Electron] Stopping Python backend...')
  if (backendProcess?.pid) {
    try {
      execSync(`taskkill /PID ${backendProcess.pid} /T /F`, { windowsHide: true, timeout: 5000, stdio: 'ignore' })
      safeLog('[Electron] Python backend stopped')
    } catch {}
    backendProcess = null
  }
}

function stopAllServices(force = false): void {
  safeLog('[Electron] Stopping all services...')
  stopBackend()
  stopRustfs()
  stopPostgres(force)
  safeLog('[Electron] All services stopped')
}

// ==================== 服务启动 ====================
async function waitForPort(port: number, timeout = 30000): Promise<boolean> {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    try {
      const socket = new (require('net').Socket)()
      const result = await new Promise<boolean>((resolve) => {
        socket.setTimeout(500)
        socket.once('connect', () => { socket.destroy(); resolve(true) })
        socket.once('error', () => { socket.destroy(); resolve(false) })
        socket.once('timeout', () => { socket.destroy(); resolve(false) })
        socket.connect(port, '127.0.0.1')
      })
      if (result) return true
    } catch {}
    await new Promise(r => setTimeout(r, 500))
  }
  return false
}

function startPostgres(): boolean {
  safeLog('[Electron] Starting PostgreSQL on port', config.pgPort)
  safeLog('[Electron] PG directory:', config.postgresDir)
  
  const pgCtl = path.join(config.postgresDir, 'bin', 'pg_ctl.exe')
  safeLog('[Electron] pg_ctl path:', pgCtl)
  safeLog('[Electron] pg_ctl exists:', fs.existsSync(pgCtl))
  const dataDir = path.join(config.postgresDir, 'data')
  const logFile = path.join(config.postgresDir, 'logfile')
  
  if (!fs.existsSync(pgCtl)) {
    safeError('[Electron] pg_ctl not found:', pgCtl)
    return false
  }
  
  // 初始化数据目录（如果不存在）
  if (!fs.existsSync(dataDir)) {
    safeLog('[Electron] Initializing PostgreSQL data directory...')
    const initdb = path.join(config.postgresDir, 'bin', 'initdb.exe')
    if (fs.existsSync(initdb)) {
      try {
        execSync(`"${initdb}" -D "${dataDir}" --encoding=UTF8 --locale=C`, {
          cwd: path.dirname(pgCtl),
          windowsHide: true,
          timeout: 60000,
          encoding: 'utf8'
        })
        safeLog('[Electron] PostgreSQL data directory initialized')
      } catch (e) {
        safeError('[Electron] Failed to initdb:', e)
        return false
      }
    }
  }
  
  try {
    pgProcess = spawn(pgCtl, ['start', '-D', dataDir, '-l', logFile], {
      cwd: path.dirname(pgCtl),
      windowsHide: true,
      env: { 
        ...process.env, 
        PGPORT: String(config.pgPort),
        PGDATA: dataDir
      }
    })
    
    pgProcess.on('close', () => { pgProcess = null })
    safeLog('[Electron] PostgreSQL start command issued')
    return true
  } catch (e) {
    safeError('[Electron] Failed to start PostgreSQL:', e)
    return false
  }
}

function startRustfs(): boolean {
  safeLog('[Electron] Starting RustFS on port', config.rustfsPort)
  safeLog('[Electron] Store directory:', config.storeDir)
  
  const rustfsPath = path.join(config.storeDir, 'rustfs.exe')
  safeLog('[Electron] rustfs path:', rustfsPath)
  safeLog('[Electron] rustfs exists:', fs.existsSync(rustfsPath))
  
  if (!fs.existsSync(rustfsPath)) {
    safeError('[Electron] rustfs.exe not found:', rustfsPath)
    return false
  }
  
  // 确保数据目录存在
  const dataDir = path.join(config.storeDir, 'data')
  try {
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true })
      safeLog('[Electron] Created RustFS data directory:', dataDir)
    }
  } catch (e) {
    safeError('[Electron] Failed to create RustFS data directory:', e)
    return false
  }
  
  try {
    rustfsProcess = spawn(rustfsPath, [
      dataDir,
      '--address', `127.0.0.1:${config.rustfsPort}`,
      '--console-address', `127.0.0.1:${config.rustfsConsolePort}`,
      '--access-key', 'rustfsadmin',
      '--secret-key', 'rustfsadmin',
      '--region', 'us-east-1'
    ], {
      cwd: config.storeDir,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe']  // 捕获 stdout 和 stderr
    })
    
    // 转发 RustFS 日志到 Electron 日志
    rustfsProcess.stdout?.on('data', (data) => {
      const lines = data.toString().trim().split('\n')
      for (const line of lines) {
        if (line.trim()) {
          safeLog(`[RustFS] ${line}`)
        }
      }
    })
    
    rustfsProcess.stderr?.on('data', (data) => {
      const lines = data.toString().trim().split('\n')
      for (const line of lines) {
        if (line.trim()) {
          safeError(`[RustFS] ${line}`)
        }
      }
    })
    
    rustfsProcess.on('close', () => { rustfsProcess = null })
    safeLog('[Electron] RustFS started, PID:', rustfsProcess.pid)
    return true
  } catch (e) {
    safeError('[Electron] Failed to start RustFS:', e)
    return false
  }
}

async function startBackend(): Promise<boolean> {
  safeLog('[Electron] Starting Python backend on port', config.backendPort)
  const backendPath = app.isPackaged 
    ? path.join(process.resourcesPath, 'backend')
    : path.join(__dirname, '../../backend')
  
  // 构建 DATABASE_URL
  const dbUrl = `postgresql://${config.dbUser}:${config.dbPassword}@${config.dbHost}:${config.pgPort}/${config.dbName}`
  
  const env = {
    ...process.env,
    HOST: '127.0.0.1',
    PORT: String(config.backendPort),
    PYTHONUNBUFFERED: '1',
    // 禁用后端自己管理 PG 和 RustFS
    USE_EMBEDDED_PG: 'false',
    DATABASE_URL: dbUrl,
    DATABASE_HOST: config.dbHost,
    DATABASE_PORT: String(config.pgPort),
    DATABASE_USER: config.dbUser,
    DATABASE_PASSWORD: config.dbPassword,
    DATABASE_NAME: config.dbName,
    PG_PORT: String(config.pgPort),
    RUSTFS_URL: `http://127.0.0.1:${config.rustfsPort}`,
    RUSTFS_ACCESS_KEY: 'rustfsadmin',
    RUSTFS_SECRET_KEY: 'rustfsadmin',
    STORE_DIR: config.storeDir,
    MODELS_DIR: config.modelsDir,
    TEMP_DIR: config.tempDir,
    DEBUG: String(config.debug),
    LOG_LEVEL: config.logLevel
  }
  
  // 检测是使用 PyInstaller 打包的可执行文件还是 Python 源码
  const packagedExe = path.join(backendPath, 'uverse-backend.exe')
  const isPackaged = fs.existsSync(packagedExe)
  
  safeLog('[Electron] Backend path:', backendPath)
  safeLog('[Electron] Packaged exe exists:', isPackaged, packagedExe)
  
  try {
    if (isPackaged) {
      // 使用 PyInstaller 打包的可执行文件
      safeLog('[Electron] Using packaged executable:', packagedExe)
      backendProcess = spawn(packagedExe, [], {
        cwd: backendPath,
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe']
      })
    } else {
      // 开发模式：使用 Python 源码
      const pythonPath = fs.existsSync(path.join(backendPath, '.venv', 'Scripts', 'python.exe'))
        ? path.join(backendPath, '.venv', 'Scripts', 'python.exe')
        : 'python.exe'
      safeLog('[Electron] Using Python interpreter:', pythonPath)
      backendProcess = spawn(pythonPath, [path.join(backendPath, 'main.py')], {
        cwd: backendPath,
        env,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe']
      })
    }
    
    // 转发 Python 日志到 Electron 日志
    backendProcess.stdout?.on('data', (data) => {
      const lines = data.toString().trim().split('\n')
      for (const line of lines) {
        if (line.trim()) {
          safeLog(`[Python] ${line}`)
        }
      }
    })
    
    backendProcess.stderr?.on('data', (data) => {
      const lines = data.toString().trim().split('\n')
      for (const line of lines) {
        if (line.trim()) {
          safeError(`[Python] ${line}`)
        }
      }
    })
    
    backendProcess.on('close', (code) => {
      if (!isQuitting) {
        safeError(`[Electron] Backend exited with code ${code}`)
      }
      backendProcess = null
    })
    
    const isReady = await waitForPort(config.backendPort, 60000)
    if (isReady) {
      safeLog('[Electron] Python backend ready')
      return true
    }
    return false
  } catch (e) {
    safeError('[Electron] Failed to start Python backend:', e)
    return false
  }
}

// ==================== 应用启动流程 ====================
async function startAllServices(): Promise<boolean> {
  // 清理残留进程
  safeLog('[Electron] Cleaning up residual processes...')
  try { execSync('taskkill /F /IM postgres.exe', { windowsHide: true, stdio: 'ignore' }) } catch {}
  try { execSync('taskkill /F /IM rustfs.exe', { windowsHide: true, stdio: 'ignore' }) } catch {}
  // 等待进程完全退出并释放文件锁
  await new Promise(r => setTimeout(r, 2000))
  
  // 启动 PostgreSQL
  if (!startPostgres()) return false
  const pgReady = await waitForPort(config.pgPort, 30000)
  if (!pgReady) {
    safeError('[Electron] PostgreSQL failed to start')
    // 清理可能残留的 PG 进程
    try { execSync('taskkill /F /IM postgres.exe', { windowsHide: true, stdio: 'ignore' }) } catch {}
    return false
  }
  safeLog('[Electron] PostgreSQL ready on port', config.pgPort)
  
  // 启动 RustFS
  if (!startRustfs()) return false
  const rustfsReady = await waitForPort(config.rustfsPort, 10000)
  if (!rustfsReady) {
    safeError('[Electron] RustFS failed to start')
    stopPostgres(true)
    return false
  }
  safeLog('[Electron] RustFS ready on port', config.rustfsPort)
  
  // 启动 Python 后端
  if (!await startBackend()) {
    safeError('[Electron] Python backend failed to start')
    stopAllServices(true)
    return false
  }
  
  safeLog('[Electron] All services started successfully')
  return true
}

// ==================== 窗口管理 ====================
async function createWindow(): Promise<void> {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize
  
  mainWindow = new BrowserWindow({
    width, height, x: 0, y: 0,
    minWidth: 800, minHeight: 600,
    title: 'Uverse',
    autoHideMenuBar: true,
    show: true,  // 立即显示窗口
    backgroundColor: '#f5f5f5',  // 设置背景色避免白屏
    webPreferences: {
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs')
    }
  })
  
  // 加载前端页面（开发模式使用 dist，生产模式也使用 dist）
  const indexPath = path.join(__dirname, '../dist/index.html')
  safeLog('[Electron] Loading:', indexPath)
  
  if (fs.existsSync(indexPath)) {
    mainWindow.loadFile(indexPath)
  } else {
    safeError('[Electron] dist/index.html not found, please run: npm run build')
    mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(`
      <html>
        <head><title>错误 - Uverse</title></head>
        <body style="font-family:sans-serif;padding:40px;text-align:center;">
          <h1>⚠️ 前端代码未编译</h1>
          <p>请先运行 <code>npm run build</code> 编译前端代码</p>
        </body>
      </html>
    `))
  }
  
  mainWindow.on('close', (e) => {
    if (isQuitting) return
    e.preventDefault()
    isQuitting = true
    
    safeLog('[Electron] Window closing, stopping services...')
    // 使用 force=true 确保服务被强制停止
    stopAllServices(true)
    
    if (tray) { tray.destroy(); tray = null }
    mainWindow?.destroy()
    app.quit()
  })
  
  mainWindow.on('closed', () => { mainWindow = null })
}

// ==================== 托盘 ====================
function createTray(): void {
  const iconPath = app.isPackaged
    ? path.join(process.resourcesPath, 'icon.png')
    : path.join(__dirname, '../build/icon.png')
  
  if (!fs.existsSync(iconPath)) {
    safeLog('[Electron] Tray icon not found:', iconPath)
    return
  }
  
  try {
    tray = new Tray(iconPath)
    tray.setToolTip('Uverse')
    
    const menu = Menu.buildFromTemplate([
      {
        label: '显示 Uverse',
        click: () => { mainWindow?.show(); mainWindow?.focus() }
      },
      {
        label: '退出',
        click: () => {
          isQuitting = true
          stopAllServices(true)
          tray?.destroy()
          mainWindow?.destroy()
          app.quit()
        }
      }
    ])
    
    tray.setContextMenu(menu)
    tray.on('click', () => tray?.popUpContextMenu())
  } catch (e) {
    safeError('[Electron] Failed to create tray:', e)
  }
}

// ==================== 应用生命周期 ====================
app.whenReady().then(async () => {
  // 初始化日志目录（必须在第一个 safeLog 之前）
  initLogDir()
  safeLog('[Electron] App ready, loading config...')
  
  // 加载配置（必须在 app.isPackaged 之后�?
  loadEnvConfig()
  resolveConfigPaths()
  
  // 1. 立即创建窗口并加载 React 应用（前端显示 Loading）
  safeLog('[Electron] Creating window and loading app...')
  await createWindow()
  createTray()
  
  // 2. 后台启动所有服务（React 会通过 API 检查状态）
  safeLog('[Electron] Starting services in background...')
  startAllServices().then(success => {
    if (!success) {
      safeError('[Electron] Failed to start services')
      // 前端会通过 API 检测到失败并显示错误
    } else {
      safeLog('[Electron] All services started successfully')
    }
  })
})

app.on('window-all-closed', () => {
  if (!isQuitting) {
    isQuitting = true
    // 窗口关闭时使用强制模式确保服务停止
    stopAllServices(true)
  }
  app.quit()
})

app.on('before-quit', (e) => {
  if (!isQuitting) {
    isQuitting = true
    e.preventDefault()
    // 延迟退出以确保服务停止
    stopAllServices(true)
    setTimeout(() => app.quit(), 500)
  }
})

// ==================== 信号处理（Ctrl+C 等）====================
// 处理 Ctrl+C 和 kill 信号，确保服务正常关闭
function handleExit(signal: string): void {
  safeLog(`[Electron] Received ${signal}, stopping services...`)
  isQuitting = true
  stopAllServices(true)
  // 强制同步刷新日志
  try {
    if (LOG_DIR) {
      const logFile = getLogFileName()
      fs.appendFileSync(logFile, `${getLogPrefix('INFO')} [Electron] Exiting on ${signal}\n`, 'utf-8')
    }
  } catch {}
  process.exit(0)
}

if (process.platform !== 'win32') {
  // Unix/Linux/Mac
  process.on('SIGINT', () => handleExit('SIGINT'))
  process.on('SIGTERM', () => handleExit('SIGTERM'))
} else {
  // Windows: 监听各种退出事件
  try {
    const readline = require('readline')
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout })
    rl.on('SIGINT', () => {
      rl.close()
      handleExit('SIGINT')
    })
  } catch {}
  
  // Windows 控制台关闭事件
  process.on('SIGHUP', () => handleExit('SIGHUP'))
  
  // Windows 特定的 Ctrl+Break
  process.on('SIGBREAK', () => handleExit('SIGBREAK'))
}

// 进程退出时的最后清理（同步执行）
process.on('exit', () => {
  // 注意：exit 事件只能执行同步代码
  if (!isQuitting) {
    try {
      // 使用 execSync 强制同步终止进程
      execSync('taskkill /F /IM postgres.exe 2>nul', { windowsHide: true, timeout: 5000 })
    } catch {}
    try {
      execSync('taskkill /F /IM rustfs.exe 2>nul', { windowsHide: true, timeout: 3000 })
    } catch {}
  }
})

// 处理未捕获的异常，确保尝试关闭服务
process.on('uncaughtException', (err) => {
  safeError('[Electron] Uncaught exception:', err)
  stopAllServices(true)
  process.exit(1)
})

// ==================== IPC ====================
ipcMain.handle('app:getVersion', () => app.getVersion())
ipcMain.handle('app:getPlatform', () => 'win32')
ipcMain.handle('app:getConfig', () => ({
  backendPort: config.backendPort,
  pgPort: config.pgPort,
  rustfsPort: config.rustfsPort
}))
ipcMain.handle('backend:getStatus', async () => ({
  running: await new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${config.backendPort}/api/health`, (res) => {
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(500, () => { req.destroy(); resolve(false) })
  }),
  pid: backendProcess?.pid
}))
ipcMain.handle('backend:restart', async () => {
  stopBackend()
  await new Promise(r => setTimeout(r, 1000))
  const success = await startBackend()
  return { success }
})
