/** 账号：启动时静默登录、同步后端用户资料。所有函数都不抛错（失败就保持本地数据）。 */

import { useStore } from '../store'
import type { Profile } from '../types/api'
import { getProfile } from './api'
import { ensureLogin, getToken, onLogin } from './auth'

onLogin((res) => useStore.getState().applyLogin(res.user))

let refreshing: Promise<Profile | null> | null = null

export function refreshProfile(): Promise<Profile | null> {
  if (!getToken()) return Promise.resolve(null)
  if (!refreshing) {
    refreshing = getProfile()
      .promise.then((p) => {
        useStore.getState().applyProfile(p)
        return p
      })
      .catch((e) => {
        console.warn('[account] 同步用户资料失败', e)
        return null
      })
      .finally(() => (refreshing = null))
  }
  return refreshing
}

/** App 启动：没有 token 就静默登录，然后同步一次资料 */
export async function bootstrap(): Promise<void> {
  if (await ensureLogin()) await refreshProfile()
}
