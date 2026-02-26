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


// ==================== 平台工具函数 ====================
const isWindows = process.platform === 'win32'

// 获取 RustFS 可执行文件名
function getRustfsExeName(): string {
  return isWindows ? 'rustfs.exe' : 'rustfs'
}

// 获取 pg_ctl 可执行文件名
function getPgCtlExeName(): string {
  return isWindows ? 'pg_ctl.exe' : 'pg_ctl'
}

// 获取 Python 可执行文件名
function getPythonExeName(): string {
  return isWindows ? 'python.exe' : 'python3'
}

// 获取虚拟环境 Python 路径
function getVenvPythonPath(backendPath: string): string {
  const venvDir = path.join(backendPath, '.venv')
  if (isWindows) {
    return path.join(venvDir, 'Scripts', 'python.exe')
  } else {
    return path.join(venvDir, 'bin', 'python3')
  }
}

// 获取后端可执行文件名
function getBackendExeName(): string {
  return isWindows ? 'uverse-backend.exe' : 'uverse-backend'
}

// ==================== 路径配置 ====================
/**
 * 获取配置根目录
 * - 调试模式: 前端源码目录 (frontend)
 * - 打包模式: userData 目录
 */
function getConfigRoot(): string {
  if (!app.isPackaged) {
    // 调试模式: __dirname 是 frontend/dist-electron，上级是 frontend
    return path.join(__dirname, '..')
  }
  // 打包模式: 使用 userData
  return app.getPath('userData')
}

/**
 * 获取 .env 文件路径
 */
function getEnvPath(): string {
  if (!app.isPackaged) {
    // 调试模式: 使用 backend/.env
    return path.join(getBackendPath(), '.env')
  }
  // 打包模式: 使用 userData/.env
  return path.join(app.getPath('userData'), '.env')
}

/**
 * 获取配置错误文件路径
 */
function getConfigErrorsPath(): string {
  if (!app.isPackaged) {
    // 调试模式: 使用 frontend/.config_errors
    return path.join(getConfigRoot(), '.config_errors')
  }
  // 打包模式: 使用 userData/.config_errors
  return path.join(app.getPath('userData'), '.config_errors')
}

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
  
  // 调试模式：使用源码目录下的 logs
  // 打包模式：使用 resources/app 目录
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
  
  // 降级到 userData（仅打包模式会走到这里）
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
  mineruOutputDir: string
  
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
  mineruOutputDir: '',
  debug: false,
  logLevel: 'INFO'
}

function getResourcesPath(): string {
  if (!app.isPackaged) {
    return path.join(__dirname, '../..')
  }
  // 打包模式：使用 process.resourcesPath（Electron 自动处理跨平台）
  // macOS: Uverse.app/Contents/Resources
  // Windows: resources/
  return process.resourcesPath
}

function loadEnvConfig(): void {
  // 获取 .env 路径（调试模式使用 backend/.env，打包模式使用 userData/.env）
  const envPath = getEnvPath()
  
  safeLog('[Electron] Checking .env at:', envPath)
  safeLog('[Electron] isPackaged:', app.isPackaged)
  
  if (!fs.existsSync(envPath)) {
    // 如果目标位置没有 .env，尝试从 Resources 复制（打包模式）或创建默认（调试模式）
    const resourcePath = getResourcesPath()
    const resourceEnvPath = path.join(resourcePath, 'backend', '.env')
    
    if (fs.existsSync(resourceEnvPath)) {
      try {
        fs.copyFileSync(resourceEnvPath, envPath)
        safeLog('[Electron] Copied .env from resources to:', envPath)
      } catch (e) {
        safeLog('[Electron] Failed to copy .env from resources:', e)
        return
      }
    } else {
      safeLog('[Electron] .env not found, using defaults')
      return
    }
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
    config.mineruOutputDir = env['MINERU_OUTPUT_DIR'] || ''
    
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

function getBackendPath(): string {
  return path.join(getResourcesPath(), 'backend')
}

function resolveConfigPaths(): void {
  const backendPath = getBackendPath()
  
  if (!backendPath) {
    safeError('[Electron] Cannot resolve backend path')
    return
  }
  
  safeLog('[Electron] Resolving paths with base:', backendPath)
  
  // 如果没有配置路径，使用默认�?backendPath 下的子目录
  // 如果是相对路径，解析为基于 backendPath 的绝对路径
  
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
  
  if (!config.tempDir) {
    config.tempDir = path.join(backendPath, 'temp')
  } else if (!path.isAbsolute(config.tempDir)) {
    config.tempDir = path.resolve(backendPath, config.tempDir)
  }
  
  if (!config.mineruOutputDir) {
    config.mineruOutputDir = path.join(backendPath, 'outputs')
  } else if (!path.isAbsolute(config.mineruOutputDir)) {
    config.mineruOutputDir = path.resolve(backendPath, config.mineruOutputDir)
  }
  
  // 调试模式下：如果 store 和 temp 目录不存在，自动创建
  // 注意：postgres 和 models 需要用户手动准备，不自动创建
  if (!app.isPackaged) {
    const dirsToCreate = [
      config.storeDir,
      config.tempDir,
      config.mineruOutputDir
    ]
    
    for (const dir of dirsToCreate) {
      if (dir && !fs.existsSync(dir)) {
        try {
          fs.mkdirSync(dir, { recursive: true })
          safeLog(`[Electron] Created directory: ${dir}`)
        } catch (e) {
          safeLog(`[Electron] Failed to create directory: ${dir}`, e)
        }
      }
    }
  }
  
  safeLog('[Electron] Resolved paths:', {
    postgresDir: config.postgresDir,
    storeDir: config.storeDir,
    modelsDir: config.modelsDir,
    tempDir: config.tempDir,
    mineruOutputDir: config.mineruOutputDir
  })
}

// ==================== 全局状�?====================
let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let pgProcess: ChildProcess | null = null
let rustfsProcess: ChildProcess | null = null
let backendProcess: ChildProcess | null = null
let isQuitting = false

// PostgreSQL 配置状态
let pgConfigStatus: 'ok' | 'not_found' | 'error' = 'ok'
let pgConfigError: string = ''


// 服务启动状态
let servicesStartPromise: Promise<boolean> | null = null
let servicesStartStatus: 'idle' | 'starting' | 'started' | 'failed' = 'idle'
let servicesStartError: string = ''
let pathCheckResult: { valid: boolean; postgres?: { valid: boolean; error?: string }; store?: { valid: boolean; error?: string }; models?: { valid: boolean; error?: string } } = { valid: true }

// ==================== 配置验证 ====================
/**
 * 验证必要路径配置是否有效
 * 返回验证结果和错误信息
 */
function validateRequiredPaths(): { valid: boolean; errors: string[] } {
  const errors: string[] = []
  
  // POSTGRES_DIR 和 STORE_DIR 的基础校验
  const basicPaths = [
    { key: 'POSTGRES_DIR', value: config.postgresDir, checkFile: path.join('bin', getPgCtlExeName()) },
    { key: 'STORE_DIR', value: config.storeDir, checkFile: getRustfsExeName() }
  ]
  
  for (const { key, value, checkFile } of basicPaths) {
    if (!value || value.trim() === '') {
      errors.push(`${key}: 路径无效`)
      continue
    }
    
    if (!fs.existsSync(value)) {
      if (!app.isPackaged && key === 'STORE_DIR') {
        try {
          fs.mkdirSync(value, { recursive: true })
          safeLog(`[Electron] Created directory: ${value}`)
        } catch (e) {
          errors.push(`${key}: 路径无效`)
          continue
        }
      } else {
        errors.push(`${key}: 路径无效`)
        continue
      }
    }
    
    if (checkFile) {
      const checkPath = path.join(value, checkFile)
      if (!fs.existsSync(checkPath)) {
        errors.push(`${key}: 路径无效`)
      }
    }
  }
  
  // MODELS_DIR 特殊校验：检查 mineru.json 和 pipeline 路径
  const modelsDir = config.modelsDir
  if (!modelsDir || modelsDir.trim() === '') {
    errors.push('MODELS_DIR: 路径无效')
  } else if (!fs.existsSync(modelsDir)) {
    errors.push('MODELS_DIR: 路径无效')
  } else {
    // 检查 mineru.json 是否存在
    const mineruJsonPath = path.join(modelsDir, 'mineru.json')
    if (!fs.existsSync(mineruJsonPath)) {
      errors.push('MODELS_DIR: 路径无效')
    } else {
      try {
        // 读取 mineru.json
        const mineruContent = fs.readFileSync(mineruJsonPath, 'utf-8')
        const mineruConfig = JSON.parse(mineruContent)
        
        // 获取 pipeline 路径
        const pipelinePath = mineruConfig['models-dir']?.['pipeline']
        if (!pipelinePath) {
          errors.push('MODELS_DIR: 路径无效')
        } else {
          // 解析 pipeline 路径（支持相对路径和绝对路径）
          let resolvedPipelinePath: string
          if (path.isAbsolute(pipelinePath)) {
            resolvedPipelinePath = pipelinePath
          } else {
            // 相对路径，基于 MODELS_DIR
            resolvedPipelinePath = path.join(modelsDir, pipelinePath)
          }
          
          // 检查 pipeline 目录是否存在且非空
          if (!fs.existsSync(resolvedPipelinePath)) {
            errors.push('MODELS_DIR: 路径无效')
          } else {
            const stats = fs.statSync(resolvedPipelinePath)
            if (!stats.isDirectory()) {
              errors.push('MODELS_DIR: 路径无效')
            } else {
              // 检查目录是否为空
              const files = fs.readdirSync(resolvedPipelinePath)
              if (files.length === 0) {
                errors.push('MODELS_DIR: 路径无效')
              } else {
                safeLog(`[Electron] MODELS_DIR validation passed, pipeline: ${resolvedPipelinePath} (${files.length} files)`)
                
                // 始终更新 pipeline 路径为基于当前 MODELS_DIR 的标准绝对路径
                try {
                  const standardPipelinePath = path.join(modelsDir, 'OpenDataLab', 'PDF-Extract-Kit-1___0')
                  const standardVlmPath = path.join(modelsDir, 'OpenDataLab', 'MinerU2___5-2509-1___2B')
                  
                  if (!mineruConfig['models-dir']) {
                    mineruConfig['models-dir'] = {}
                  }
                  
                  // 如果标准 pipeline 路径存在，则使用它
                  if (fs.existsSync(standardPipelinePath)) {
                    mineruConfig['models-dir']['pipeline'] = standardPipelinePath
                    safeLog(`[Electron] Updated mineru.json pipeline path to: ${standardPipelinePath}`)
                  } else {
                    // 否则使用解析到的路径
                    mineruConfig['models-dir']['pipeline'] = resolvedPipelinePath
                    safeLog(`[Electron] Updated mineru.json pipeline path to: ${resolvedPipelinePath}`)
                  }
                  
                  // 同时更新 vlm 路径（如果存在）
                  if (fs.existsSync(standardVlmPath)) {
                    mineruConfig['models-dir']['vlm'] = standardVlmPath
                    safeLog(`[Electron] Updated mineru.json vlm path to: ${standardVlmPath}`)
                  }
                  
                  fs.writeFileSync(mineruJsonPath, JSON.stringify(mineruConfig, null, 4), 'utf-8')
                  safeLog(`[Electron] Saved mineru.json successfully`)
                } catch (e) {
                  safeLog(`[Electron] Failed to update mineru.json:`, e)
                }
              }
            }
          }
        }
      } catch (e) {
        errors.push('MODELS_DIR: 路径无效')
      }
    }
  }
  
  return { valid: errors.length === 0, errors }
}

// ==================== 服务停止 ====================
function stopPostgres(force = false): void {
  safeLog('[Electron] Stopping PostgreSQL...')
  const pgCtl = path.join(config.postgresDir, 'bin', getPgCtlExeName())
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

function stopRustfs(force = false): void {
  safeLog('[Electron] Stopping RustFS...')
  
  if (rustfsProcess?.pid) {
    try {
      if (isWindows) {
        execSync(`taskkill /PID ${rustfsProcess.pid} /T /F`, { windowsHide: true, timeout: 5000, stdio: 'ignore' })
      } else {
        // macOS/Linux: 尝试优雅关闭，然后强制关闭
        try {
          process.kill(rustfsProcess.pid, 'SIGTERM')
          if (!force) {
            // 等待进程自行关闭
            let waitCount = 0
            while (waitCount < 30) {
              try {
                process.kill(rustfsProcess.pid, 0)
                execSync('sleep 0.1', { stdio: 'ignore' })
                waitCount++
              } catch {
                break
              }
            }
          }
          // 强制关闭
          process.kill(rustfsProcess.pid, 'SIGKILL')
        } catch {}
      }
      safeLog('[Electron] RustFS stopped via PID')
      rustfsProcess = null
      return
    } catch {}
  }
  
  // 兜底：通过进程名杀死
  if (isWindows) {
    try {
      execSync(`taskkill /F /IM ${getRustfsExeName()}`, { windowsHide: true, timeout: 3000, stdio: 'ignore' })
      safeLog('[Electron] RustFS stopped via taskkill')
    } catch {}
  } else {
    try {
      execSync(`pkill -f "${getRustfsExeName()}" || true`, { stdio: 'ignore' })
    } catch {}
  }
  rustfsProcess = null
}

function stopBackend(force = false): void {
  safeLog('[Electron] Stopping Python backend...')
  if (!backendProcess?.pid) {
    backendProcess = null
    return
  }
  
  try {
    if (isWindows) {
      // Windows: 使用 taskkill
      const cmd = force 
        ? `taskkill /PID ${backendProcess.pid} /T /F`
        : `taskkill /PID ${backendProcess.pid} /T`;
      execSync(cmd, { windowsHide: true, timeout: 5000, stdio: 'ignore' })
    } else {
      // macOS/Linux: 先尝试优雅关闭 (SIGTERM)，如果失败则强制关闭 (SIGKILL)
      try {
        // 发送 SIGTERM 信号，让后端有机会优雅关闭
        process.kill(backendProcess.pid, 'SIGTERM')
        safeLog('[Electron] SIGTERM sent to backend, waiting for graceful shutdown...')
        
        if (!force) {
          // 非强制模式：等待后端自行关闭（最多5秒）
          let waitCount = 0
          while (waitCount < 50) {
            try {
              // 检查进程是否还存在
              process.kill(backendProcess.pid, 0)
              // 进程还存在，等待
              execSync('sleep 0.1', { stdio: 'ignore' })
              waitCount++
            } catch {
              // 进程已不存在
              safeLog('[Electron] Backend stopped gracefully')
              backendProcess = null
              return
            }
          }
          safeLog('[Electron] Backend did not stop gracefully, forcing...')
        }
        
        // 强制关闭
        process.kill(backendProcess.pid, 'SIGKILL')
        safeLog('[Electron] Backend stopped with SIGKILL')
      } catch (e) {
        // 进程可能已经被终止
        safeLog('[Electron] Backend process already terminated')
      }
    }
    safeLog('[Electron] Python backend stopped')
  } catch (e) {
    safeLog('[Electron] Error stopping backend:', e)
  }
  backendProcess = null
}

function stopAllServices(force = false): void {
  safeLog('[Electron] Stopping all services...')
  stopBackend(force)
  stopRustfs(force)
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
  
  const pgCtl = path.join(config.postgresDir, 'bin', getPgCtlExeName())
  safeLog('[Electron] pg_ctl path:', pgCtl)
  safeLog('[Electron] pg_ctl exists:', fs.existsSync(pgCtl))
  const dataDir = path.join(config.postgresDir, 'data')
  const logFile = path.join(config.postgresDir, 'logfile')
  
  if (!fs.existsSync(pgCtl)) {
    safeError('[Electron] pg_ctl not found:', pgCtl)
    pgConfigStatus = 'not_found'
    pgConfigError = `PostgreSQL 未找到: ${pgCtl}\n请在设置中配置正确的 PostgreSQL 路径`
    return false
  }
  
  // 重置状态
  pgConfigStatus = 'ok'
  pgConfigError = ''
  
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
    pgConfigStatus = 'ok'
    return true
  } catch (e: any) {
    safeError('[Electron] Failed to start PostgreSQL:', e)
    pgConfigStatus = 'error'
    pgConfigError = `启动 PostgreSQL 失败: ${e?.message || String(e)}`
    return false
  }
}

function startRustfs(): boolean {
  safeLog('[Electron] Starting RustFS on port', config.rustfsPort)
  safeLog('[Electron] Store directory:', config.storeDir)
  
  const rustfsPath = path.join(config.storeDir, getRustfsExeName())
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
    
    // 转发 RustFS 日志到 Electron 日志（只监听 stdout）
    rustfsProcess.stdout?.on('data', (data) => {
      const lines = data.toString().trim().split('\n')
      for (const line of lines) {
        if (line.trim()) {
          safeLog(`[RustFS] ${line}`)
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
  const backendPath = getBackendPath()
  
  if (!backendPath || !fs.existsSync(backendPath)) {
    safeError('[Electron] Backend directory not found:', backendPath)
    return false
  }
  
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
    MINERU_OUTPUT_DIR: config.mineruOutputDir,
    DEBUG: String(config.debug),
    LOG_LEVEL: config.logLevel
  }
  
  // 检测是使用 PyInstaller 打包的可执行文件还是 Python 源码
  const packagedExe = path.join(backendPath, getBackendExeName())
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
      const venvPython = getVenvPythonPath(backendPath)
      const pythonPath = fs.existsSync(venvPython) ? venvPython : getPythonExeName()
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
  try { execSync(`taskkill /F /IM ${getRustfsExeName()}`, { windowsHide: true, stdio: 'ignore' }) } catch {}
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
  safeLog('[Electron] ==========================================')
  safeLog('[Electron] App ready')
  safeLog('[Electron] isPackaged:', app.isPackaged)
  safeLog('[Electron] ==========================================')
  
  // 加载配置（必须在 app.isPackaged 之后）
  safeLog('[Electron] Step 1: Loading config...')
  loadEnvConfig()
  
  safeLog('[Electron] Step 2: Resolving paths...')
  resolveConfigPaths()
  
  // 验证必要路径配置
  safeLog('[Electron] Step 3: Validating required paths...')
  const validation = validateRequiredPaths()
  safeLog('[Electron] Validation result:', validation.valid ? 'PASSED' : 'FAILED')
  if (!validation.valid) {
    safeLog('[Electron] Validation errors:', validation.errors.join('; '))
  }
  
  // 1. 立即创建窗口并加载 React 应用
  safeLog('[Electron] Creating window and loading app...')
  await createWindow()
  createTray()
  
  if (!validation.valid) {
    // 配置不完整，不启动服务，让用户去设置页面配置
    safeLog('[Electron] Configuration incomplete, skipping service startup')
    safeLog('[Electron] Validation errors:', validation.errors)
    servicesStartStatus = 'idle'
    servicesStartError = '配置不完整：' + validation.errors.join('; ')
    
    // 通知前端配置错误（通过 IPC 查询时会返回）
    pathCheckResult = { 
      valid: false, 
      postgres: { valid: false, error: validation.errors.find(e => e.includes('POSTGRES_DIR')) },
      store: { valid: false, error: validation.errors.find(e => e.includes('STORE_DIR')) },
      models: { valid: false, error: validation.errors.find(e => e.includes('MODELS_DIR')) }
    }
    
    // 保存错误到文件，前端可以读取
    try {
      const errorFile = getConfigErrorsPath()
      fs.writeFileSync(errorFile, JSON.stringify(validation.errors), 'utf-8')
    } catch {}
    
    return
  }
  
  // 2. 配置验证通过，后台启动所有服务
  safeLog('[Electron] Configuration valid, starting services...')
  servicesStartStatus = 'starting'
  
  // 清除之前的配置错误
  try {
    const errorFile = getConfigErrorsPath()
    if (fs.existsSync(errorFile)) {
      fs.unlinkSync(errorFile)
    }
  } catch {}
  
  startAllServices().then(success => {
    if (!success) {
      safeError('[Electron] Failed to start services')
      servicesStartStatus = 'failed'
    } else {
      safeLog('[Electron] All services started successfully')
      servicesStartStatus = 'started'
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

app.on('before-quit', async (e) => {
  if (!isQuitting) {
    isQuitting = true
    e.preventDefault()
    safeLog('[Electron] before-quit: Gracefully stopping services...')
    
    // 先尝试优雅关闭（非强制模式），给后端时间完成活跃任务
    stopAllServices(false)
    
    // 等待更长时间让后端完成清理（最多8秒）
    let waitCount = 0
    const maxWait = 80 // 80 * 100ms = 8秒
    while (waitCount < maxWait) {
      // 检查后端是否已停止
      if (!backendProcess && !rustfsProcess) {
        safeLog('[Electron] All services stopped gracefully')
        break
      }
      await new Promise(r => setTimeout(r, 100))
      waitCount++
    }
    
    if (waitCount >= maxWait) {
      safeLog('[Electron] Some services still running, forcing shutdown...')
      stopAllServices(true)
    }
    
    app.quit()
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
  pid: backendProcess?.pid,
  pgConfigStatus,
  pgConfigError,
  servicesStartStatus,
  servicesStartError,
  pathCheck: pathCheckResult
}))
ipcMain.handle('backend:restart', async () => {
  stopBackend()
  await new Promise(r => setTimeout(r, 1000))
  const success = await startBackend()
  return { success }
})
ipcMain.handle('backend:waitForStart', async () => {
  if (servicesStartPromise) {
    await servicesStartPromise
  }
  return {
    status: servicesStartStatus,
    error: servicesStartError,
    pathCheck: pathCheckResult
  }
})

// 启动所有服务（由前端调用，配置正确后启动）
ipcMain.handle('services:start', async () => {
  safeLog('[IPC] Received request to start services')
  
  // 如果服务已经在启动中或已启动，返回当前状态
  if (servicesStartStatus === 'starting' || servicesStartStatus === 'started') {
    return { success: servicesStartStatus === 'started', status: servicesStartStatus, error: servicesStartError }
  }
  
  // 验证配置
  const validation = validateRequiredPaths()
  if (!validation.valid) {
    safeLog('[IPC] Cannot start services: configuration invalid')
    return { success: false, status: 'idle', error: '配置不完整：' + validation.errors.join('; ') }
  }
  
  // 启动服务
  servicesStartStatus = 'starting'
  servicesStartError = ''
  
  try {
    const success = await startAllServices()
    servicesStartStatus = success ? 'started' : 'failed'
    if (!success) {
      servicesStartError = '服务启动失败'
    }
    return { success, status: servicesStartStatus, error: servicesStartError }
  } catch (error: any) {
    safeError('[IPC] Failed to start services:', error)
    servicesStartStatus = 'failed'
    servicesStartError = error.message || '服务启动失败'
    return { success: false, status: 'failed', error: servicesStartError }
  }
})

ipcMain.handle('config:getFromEnv', () => {
  // 获取 .env 路径（调试模式使用 backend/.env，打包模式使用 userData/.env）
  const envPath = getEnvPath()
  safeLog('[IPC] getConfigFromEnv - reading from:', envPath)
  safeLog('[IPC] isPackaged:', app.isPackaged)
  
  const configs: Array<{key: string; value: string; description: string; category: string}> = []
  
  try {
    if (!fs.existsSync(envPath)) {
      return { success: false, configs: [], message: '.env file not found' }
    }
    
    const content = fs.readFileSync(envPath, 'utf-8')
    const categoryMap: Record<string, string> = {
      'PORT': 'basic', 'DATABASE_PORT': 'basic',
      'POSTGRES_DIR': 'path', 'STORE_DIR': 'path', 'MODELS_DIR': 'path', 'TEMP_DIR': 'path',
      'MINERU_OUTPUT_DIR': 'mineru',
      'MINERU_BACKEND': 'mineru', 'MINERU_DEVICE': 'mineru', 'MINERU_VRAM': 'mineru',
      'MINERU_VIRTUAL_VRAM_SIZE': 'mineru',
      'DEBUG': 'other', 'LOG_LEVEL': 'other'
    }
    const descriptionMap: Record<string, string> = {
      'PORT': '后端服务端口',
      'DATABASE_PORT': 'PostgreSQL 端口',
      'POSTGRES_DIR': 'PostgreSQL 安装目录',
      'STORE_DIR': '存储目录（包含 RustFS 数据）',
      'MODELS_DIR': 'AI 模型目录（包含 OpenDataLab 等模型）',
      'TEMP_DIR': '临时文件目录',
      'MINERU_OUTPUT_DIR': 'PDF 解析输出目录',
      'MINERU_BACKEND': 'MinerU 解析后端 (auto/pytorch/mps)',
      'MINERU_DEVICE': 'MinerU 设备模式 (cuda/cpu)',
      'MINERU_VRAM': 'MinerU 显存限制',
      'MINERU_VIRTUAL_VRAM_SIZE': 'MinerU 虚拟显存大小',
      'DEBUG': '调试模式',
      'LOG_LEVEL': '日志级别'
    }
    
    for (const line of content.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      
      const eqIndex = trimmed.indexOf('=')
      if (eqIndex === -1) continue
      
      const key = trimmed.substring(0, eqIndex).trim()
      let value = trimmed.substring(eqIndex + 1).trim()
      
      if ((value.startsWith('"') && value.endsWith('"')) ||
          (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1)
      }
      
      configs.push({
        key,
        value,
        description: descriptionMap[key] || '',
        category: categoryMap[key] || 'other'
      })
    }
    
    return { success: true, configs }
  } catch (e: any) {
    return { success: false, configs: [], message: e.message }
  }
})

ipcMain.handle('config:saveToEnv', async (_event, configs: Record<string, string>) => {
  safeLog('[IPC] config:saveToEnv called')
  safeLog('[IPC] Config keys:', Object.keys(configs).join(', '))
  safeLog('[IPC] isPackaged:', app.isPackaged)
  
  // 获取 .env 路径（调试模式使用 backend/.env，打包模式使用 userData/.env）
  const envPath = getEnvPath()
  safeLog('[IPC] Will save .env to:', envPath)
  
  try {
    // 读取现有配置
    const existingConfigs: Record<string, string> = {}
    if (fs.existsSync(envPath)) {
      const content = fs.readFileSync(envPath, 'utf-8')
      for (const line of content.split('\n')) {
        const trimmed = line.trim()
        if (!trimmed || trimmed.startsWith('#')) continue
        const eqIndex = trimmed.indexOf('=')
        if (eqIndex === -1) continue
        const key = trimmed.substring(0, eqIndex).trim()
        let value = trimmed.substring(eqIndex + 1).trim()
        if ((value.startsWith('"') && value.endsWith('"')) ||
            (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1)
        }
        existingConfigs[key] = value
      }
    }
    
    // 合并新配置
    Object.assign(existingConfigs, configs)
    
    // 写入 .env
    const lines: string[] = []
    const basicKeys = ['PORT', 'DATABASE_HOST', 'DATABASE_PORT', 'DATABASE_USER', 'DATABASE_PASSWORD', 'DATABASE_NAME']
    const pathKeys = ['POSTGRES_DIR', 'STORE_DIR', 'MODELS_DIR', 'TEMP_DIR']
    const mineruKeys = ['MINERU_OUTPUT_DIR', 'MINERU_BACKEND', 'MINERU_DEVICE', 'MINERU_VRAM', 'MINERU_VIRTUAL_VRAM_SIZE']
    
    lines.push('# Basic Configuration')
    for (const key of basicKeys) {
      if (existingConfigs[key] !== undefined) lines.push(`${key}=${existingConfigs[key]}`)
    }
    lines.push('')
    
    lines.push('# Path Configuration')
    for (const key of pathKeys) {
      if (existingConfigs[key] !== undefined) {
        const value = existingConfigs[key]
        const needsQuotes = value.includes(' ') || value.includes('#') || value.includes('=')
        lines.push(`${key}=${needsQuotes ? `"${value}"` : value}`)
      }
    }
    lines.push('')
    
    lines.push('# MinerU Configuration')
    for (const key of mineruKeys) {
      if (existingConfigs[key] !== undefined) {
        const value = existingConfigs[key]
        const needsQuotes = value.includes(' ') || value.includes('#') || value.includes('=')
        lines.push(`${key}=${needsQuotes ? `"${value}"` : value}`)
      }
    }
    
    fs.writeFileSync(envPath, lines.join('\n'), 'utf-8')
    safeLog('[IPC] Saved .env to:', envPath)
    
    // 如果 MODELS_DIR 配置了，同步更新 mineru.json
    safeLog('[IPC] Checking MODELS_DIR in configs:', !!configs['MODELS_DIR'])
    if (configs['MODELS_DIR']) {
      try {
        const modelsDir = configs['MODELS_DIR']
        const mineruJsonPath = path.join(modelsDir, 'mineru.json')
        safeLog('[IPC] Checking mineru.json at:', mineruJsonPath)
        
        const mineruExists = fs.existsSync(mineruJsonPath)
        safeLog('[IPC] mineru.json exists:', mineruExists)
        
        if (mineruExists) {
          safeLog('[IPC] Found mineru.json, reading...')
          const mineruContent = fs.readFileSync(mineruJsonPath, 'utf-8')
          safeLog('[IPC] mineru.json content length:', mineruContent.length)
          
          const mineruConfig = JSON.parse(mineruContent)
          const pipelinePath = path.join(modelsDir, 'OpenDataLab', 'PDF-Extract-Kit-1___0')
          const vlmPath = path.join(modelsDir, 'OpenDataLab', 'MinerU2___5-2509-1___2B')
          
          safeLog('[IPC] Pipeline path:', pipelinePath)
          safeLog('[IPC] Pipeline exists:', fs.existsSync(pipelinePath))
          safeLog('[IPC] VLM path:', vlmPath)
          safeLog('[IPC] VLM exists:', fs.existsSync(vlmPath))
          
          if (!mineruConfig['models-dir']) {
            safeLog('[IPC] Creating models-dir object')
            mineruConfig['models-dir'] = {}
          }
          
          if (fs.existsSync(pipelinePath)) {
            mineruConfig['models-dir']['pipeline'] = pipelinePath
            safeLog('[IPC] ✓ Updated pipeline path')
          } else {
            safeLog('[IPC] ✗ Pipeline path not found, skipping')
          }
          
          if (fs.existsSync(vlmPath)) {
            mineruConfig['models-dir']['vlm'] = vlmPath
            safeLog('[IPC] ✓ Updated vlm path')
          } else {
            safeLog('[IPC] ✗ VLM path not found, skipping')
          }
          
          safeLog('[IPC] Writing mineru.json...')
          fs.writeFileSync(mineruJsonPath, JSON.stringify(mineruConfig, null, 4), 'utf-8')
          safeLog('[IPC] ✓ Saved mineru.json successfully')
        } else {
          safeLog('[IPC] ✗ mineru.json not found at:', mineruJsonPath)
        }
      } catch (e: any) {
        safeError('[IPC] ✗ Failed to update mineru.json:', e)
        safeError('[IPC] Error stack:', e.stack)
        // 继续返回成功，因为 .env 保存成功了
      }
    } else {
      safeLog('[IPC] MODELS_DIR not provided, skipping mineru.json update')
    }
    
    safeLog('[IPC] config:saveToEnv completed successfully')
    return { success: true }
  } catch (e: any) {
    return { success: false, message: e.message }
  }
})

// 检查路径有效性（保存配置前调用）
ipcMain.handle('config:checkPaths', async (_event, paths: Record<string, string>) => {
  safeLog('[IPC] Checking paths:', Object.keys(paths))
  const errors: Record<string, string> = {}
  
  // 获取 backend 路径用于解析相对路径
  const backendPath = getBackendPath()
  
  for (const [key, value] of Object.entries(paths)) {
    if (!value || value.trim() === '') {
      errors[key] = '路径无效'
      continue
    }
    
    // 解析路径（支持相对和绝对路径）
    let resolvedPath: string
    if (path.isAbsolute(value)) {
      resolvedPath = value
    } else if (backendPath) {
      resolvedPath = path.resolve(backendPath, value)
    } else {
      errors[key] = '路径无效'
      continue
    }
    
    // 检查目录是否存在
    if (!fs.existsSync(resolvedPath)) {
      errors[key] = '路径无效'
      continue
    }
    
    // 特定路径的额外检查
    if (key === 'POSTGRES_DIR') {
      const pgCtl = path.join(resolvedPath, 'bin', getPgCtlExeName())
      if (!fs.existsSync(pgCtl)) {
        errors[key] = '路径无效'
      }
    } else if (key === 'STORE_DIR') {
      const rustfs = path.join(resolvedPath, getRustfsExeName())
      if (!fs.existsSync(rustfs)) {
        errors[key] = '路径无效'
      }
    } else if (key === 'MODELS_DIR') {
      // 检查 mineru.json
      const mineruJsonPath = path.join(resolvedPath, 'mineru.json')
      if (!fs.existsSync(mineruJsonPath)) {
        errors[key] = '路径无效'
      } else {
        try {
          const mineruContent = fs.readFileSync(mineruJsonPath, 'utf-8')
          const mineruConfig = JSON.parse(mineruContent)
          const pipelinePath = mineruConfig['models-dir']?.['pipeline']
          
          if (!pipelinePath) {
            errors[key] = '路径无效'
          } else {
            // 解析 pipeline 路径
            let resolvedPipelinePath: string
            if (path.isAbsolute(pipelinePath)) {
              resolvedPipelinePath = pipelinePath
            } else {
              resolvedPipelinePath = path.join(resolvedPath, pipelinePath)
            }
            
            if (!fs.existsSync(resolvedPipelinePath)) {
              errors[key] = '路径无效'
            } else {
              const files = fs.readdirSync(resolvedPipelinePath)
              if (files.length === 0) {
                errors[key] = '路径无效'
              }
            }
          }
        } catch (e) {
          errors[key] = '路径无效'
        }
      }
    }
  }
  
  const valid = Object.keys(errors).length === 0
  safeLog('[IPC] Path check result:', valid ? 'valid' : `invalid (${Object.keys(errors).join(', ')})`)
  return { valid, errors }
})

ipcMain.handle('shell:openExternal', async (_event, url: string) => {
  const { shell } = require('electron')
  await shell.openExternal(url)
})

ipcMain.handle('log:write', (_event, level: string, msg: string) => {
  writeLogToFile(level, `[Frontend] ${msg}`)
})

