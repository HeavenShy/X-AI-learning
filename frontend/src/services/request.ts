import Taro from '@tarojs/taro'

import { ErrorCode, type ApiEnvelope } from '../types/api'

export const API_BASE = (process.env.TARO_APP_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '')

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

/** POST JSON，后端统一返回 {code, message, data}；可中止 */
export function post<T>(path: string, data: unknown, timeout: number): Pending<T> {
  let task: Taro.RequestTask<ApiEnvelope<T>> | null = null
  let aborted = false
  const promise = new Promise<T>((resolve, reject) => {
    task = Taro.request<ApiEnvelope<T>>({
      url: `${API_BASE}${path}`,
      method: 'POST',
      data: data as Record<string, unknown>,
      header: { 'content-type': 'application/json' },
      timeout,
      success: (res) => {
        const body = res.data
        if (body && typeof body === 'object' && 'code' in body) {
          if (body.code === ErrorCode.OK && body.data != null) resolve(body.data)
          else reject(new ApiError(body.code, body.message))
          return
        }
        reject(new ApiError(ErrorCode.INTERNAL_ERROR, `服务返回异常（HTTP ${res.statusCode}）`))
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
