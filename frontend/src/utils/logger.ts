/**
 * 前端日志工具
 * 将日志发送到 Electron 主进程写入文件
 */

// 日志级别
export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR'

// 是否在 Electron 环境中
const isElectron = () => {
  return typeof window !== 'undefined' && 
         (window as any).electronAPI?.logWrite !== undefined
}

// 写入日志
const writeLog = async (level: LogLevel, message: string, ...args: any[]) => {
  const timestamp = new Date().toISOString()
  const formattedMessage = args.length > 0 
    ? `${message} ${args.map(arg => typeof arg === 'object' ? JSON.stringify(arg) : String(arg)).join(' ')}`
    : message
  
  // 同时输出到浏览器控制台
  switch (level) {
    case 'DEBUG':
      console.debug(`[${timestamp}] [${level}]`, formattedMessage)
      break
    case 'INFO':
      console.info(`[${timestamp}] [${level}]`, formattedMessage)
      break
    case 'WARN':
      console.warn(`[${timestamp}] [${level}]`, formattedMessage)
      break
    case 'ERROR':
      console.error(`[${timestamp}] [${level}]`, formattedMessage)
      break
  }
  
  // 发送到 Electron 主进程写入文件
  if (isElectron()) {
    try {
      await (window as any).electronAPI.logWrite(level, formattedMessage)
    } catch (e) {
      // 如果写入失败，只在控制台输出
      console.error('[Logger] Failed to write log to file:', e)
    }
  }
}

// 日志工具对象
export const logger = {
  debug: (message: string, ...args: any[]) => writeLog('DEBUG', message, ...args),
  info: (message: string, ...args: any[]) => writeLog('INFO', message, ...args),
  warn: (message: string, ...args: any[]) => writeLog('WARN', message, ...args),
  error: (message: string, ...args: any[]) => writeLog('ERROR', message, ...args),
}

// 默认导出
export default logger
