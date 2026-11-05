/**
 * 登录态：微信静默登录（wx.login → 后端 /user/login）拿 JWT，存在本地。
 * - 所有业务请求经 authed() 自动带 token；后端返回 4010 时清掉 token、静默重登一次再重发。
 * - 登录失败（网络不通、H5 没有 wx.login）不拦用户：出题和报告照常匿名可用，只是不保存记录。
 */

import Taro from '@tarojs/taro'

import { withReauth } from '../core/reauth'
import { ErrorCode, type LoginResponse } from '../types/api'
import { ApiError, send, type Method, type Pending } from './request'

const TOKEN_KEY = 'yhyd.token'
const LOGIN_TIMEOUT = 15_000

export function getToken(): string | null {
  try {
    return (Taro.getStorageSync(TOKEN_KEY) as string) || null
  } catch {
    return null
  }
}

function setToken(token: string | null) {
  try {
    if (token) Taro.setStorageSync(TOKEN_KEY, token)
    else Taro.removeStorageSync(TOKEN_KEY)
  } catch (e) {
    console.warn('[auth] 保存 token 失败', e)
  }
}

type LoginListener = (res: LoginResponse) => void
const listeners: LoginListener[] = []

/** 每次登录成功（含过期后静默重登）时通知，store 用它同步用户资料 */
export function onLogin(fn: LoginListener) {
  listeners.push(fn)
}

let inflight: Promise<LoginResponse | null> | null = null

async function doLogin(): Promise<LoginResponse | null> {
  try {
    const { code } = await Taro.login({ timeout: LOGIN_TIMEOUT })
    if (!code) throw new Error('wx.login 没有返回 code')
    const res = await send<LoginResponse>({
      method: 'POST',
      path: '/api/v1/user/login',
      data: { code },
      timeout: LOGIN_TIMEOUT
    }).promise
    setToken(res.token)
    listeners.forEach((fn) => fn(res))
    return res
  } catch (e) {
    console.warn('[auth] 登录失败，先按未登录使用', e)
    return null
  }
}

/** 静默登录。并发调用共用同一次登录 */
export function login(): Promise<LoginResponse | null> {
  if (!inflight) inflight = doLogin().finally(() => (inflight = null))
  return inflight
}

/** 有 token 就直接用；没有就登录一次 */
export async function ensureLogin(): Promise<string | null> {
  return getToken() ?? (await login())?.token ?? null
}

const isUnauthorized = (e: unknown) => e instanceof ApiError && e.code === ErrorCode.UNAUTHORIZED

/** 带登录态的请求：自动附加 token，过期时重登一次再重发；可中止 */
export function authed<T>(method: Method, path: string, data: unknown, timeout: number): Pending<T> {
  let current: Pending<T> | null = null
  let aborted = false
  const attempt = async (token: string | null) => {
    if (aborted) throw new ApiError(ErrorCode.ABORTED, '已取消')
    current = send<T>({ method, path, data, timeout, token })
    return current.promise
  }
  const promise = (async () => {
    // 刚启动时登录可能还在路上：等它完成，避免这次出题没带上 token、没被保存
    if (!getToken() && inflight) await inflight
    return withReauth(attempt, {
      getToken,
      relogin: async () => {
        setToken(null)
        return (await login())?.token ?? null
      },
      isUnauthorized
    })
  })()
  return {
    promise,
    abort: () => {
      aborted = true
      current?.abort()
    }
  }
}
