import Taro from '@tarojs/taro'

import { ErrorCode, type ApiEnvelope } from '../types/api'

/**
 * 构建时由 Taro（webpack DefinePlugin）把 process.env.TARO_APP_API_BASE 替换成 .env 里的值。
 * 小程序 / H5 运行时没有 process：万一变量没配置、表达式没被替换，会抛 ReferenceError，这里兜底。
 * 注意不能用 typeof process 判断——它不会被替换，运行时恒为 'undefined'。
 */
function readApiBase(): string {
  try {
    const v = process.env.TARO_APP_API_BASE
    if (v) return v
  } catch {
    // 变量未配置
  }
  return 'http://127.0.0.1:8000'
}

export const API_BASE = readApiBase().replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    public code: number,
    message: string
  ) {
    super(message)
  }
}

export interface Pending<T> {
  promise: Promise<T>
  abort: () => void
}

export type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

export interface SendOptions {
  method: Method
  path: string
  data?: unknown
  timeout: number
  /** 有值时带上 Authorization: Bearer <token> */
  token?: string | null
  /** 成功时 data 允许为 null（删除类接口），此时 resolve(null) */
  allowEmpty?: boolean
}

/** 解析后端信封 {code, message, data}；不是信封时按服务异常处理 */
export function unwrap<T>(body: unknown, statusCode: number, allowEmpty = false): T {
  if (body && typeof body === 'object' && 'code' in body) {
    const env = body as ApiEnvelope<T>
    if (env.code === ErrorCode.OK && (env.data != null || allowEmpty)) return env.data as T
    throw new ApiError(env.code, env.message)
  }
  throw new ApiError(ErrorCode.INTERNAL_ERROR, `服务返回异常（HTTP ${statusCode}）`)
}

/** 发一次请求。后端统一返回 {code, message, data}；可中止。登录态处理见 services/auth.ts */
export function send<T>({ method, path, data, timeout, token, allowEmpty }: SendOptions): Pending<T> {
  let task: Taro.RequestTask<ApiEnvelope<T>> | null = null
  let aborted = false
  const header: Record<string, string> = { 'content-type': 'application/json' }
  if (token) header.Authorization = `Bearer ${token}`
  const promise = new Promise<T>((resolve, reject) => {
    task = Taro.request<ApiEnvelope<T>>({
      url: `${API_BASE}${path}`,
      method,
      data: data as Record<string, unknown>,
      header,
      timeout,
      success: (res) => {
        try {
          resolve(unwrap<T>(res.data, res.statusCode, allowEmpty))
        } catch (e) {
          reject(e)
        }
      },
      fail: (err) => {
        if (aborted || /abort/i.test(err.errMsg || '')) reject(new ApiError(ErrorCode.ABORTED, '已取消'))
        else reject(new ApiError(ErrorCode.NETWORK, '网络好像断了，没连上服务'))
      }
    })
  })
  return {
    promise,
    abort: () => {
      aborted = true
      task?.abort()
    }
  }
}

export interface UploadOptions {
  path: string
  /** 本地临时文件路径（chooseMessageFile 返回的 path） */
  filePath: string
  /** multipart 字段名，后端是 file */
  name: string
  timeout: number
  token?: string | null
}

/** 上传一个文件（multipart）。小程序上传只能走 uploadFile，不能用 request；返回的 data 是字符串，需要自己解析 */
export function upload<T>({ path, filePath, name, timeout, token }: UploadOptions): Pending<T> {
  let task: Taro.UploadTask | null = null
  let aborted = false
  const header: Record<string, string> = {}
  if (token) header.Authorization = `Bearer ${token}`
  const promise = new Promise<T>((resolve, reject) => {
    task = Taro.uploadFile({
      url: `${API_BASE}${path}`,
      filePath,
      name,
      header,
      timeout,
      success: (res) => {
        let body: unknown = res.data
        if (typeof body === 'string') {
          try {
            body = JSON.parse(body)
          } catch {
            reject(new ApiError(ErrorCode.INTERNAL_ERROR, `服务返回异常（HTTP ${res.statusCode}）`))
            return
          }
        }
        try {
          resolve(unwrap<T>(body, res.statusCode))
        } catch (e) {
          reject(e)
        }
      },
      fail: (err) => {
        if (aborted || /abort/i.test(err.errMsg || '')) reject(new ApiError(ErrorCode.ABORTED, '已取消'))
        else reject(new ApiError(ErrorCode.NETWORK, '网络好像断了，没传上去'))
      }
    }) as unknown as Taro.UploadTask
  })
  return {
    promise,
    abort: () => {
      aborted = true
      task?.abort()
    }
  }
}
