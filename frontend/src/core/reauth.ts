/**
 * 登录过期自动续上：请求返回“未登录”（4010）时，重新静默登录一次，用新 token 重发。
 * 只重试一次，避免死循环；重新登录失败就把原错误抛给调用方。
 */

export interface ReauthDeps {
  getToken: () => string | null
  relogin: () => Promise<string | null>
  isUnauthorized: (err: unknown) => boolean
}

export async function withReauth<T>(attempt: (token: string | null) => Promise<T>, deps: ReauthDeps): Promise<T> {
  try {
    return await attempt(deps.getToken())
  } catch (err) {
    if (!deps.isUnauthorized(err)) throw err
    const fresh = await deps.relogin()
    if (!fresh) throw err
    return attempt(fresh)
  }
}
