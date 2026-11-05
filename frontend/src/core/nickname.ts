/** 昵称：与后端 user_service 规则一致（去首尾空白，1–20 个字） */

export const NICKNAME_MAX = 20
export const DEFAULT_AVATAR_CHAR = '学'

const normalize = (s: string) => s.trim().split(/\s+/).filter(Boolean).join(' ')

/** 原型的头像是昵称首字（“林”）；按字符而不是 UTF-16 码元取，emoji 不会被截断 */
export function avatarChar(nickname: string): string {
  return Array.from(normalize(nickname))[0] ?? DEFAULT_AVATAR_CHAR
}

export function validateNickname(raw: string): string | null {
  const n = normalize(raw)
  if (!n) return '昵称不能为空'
  if (Array.from(n).length > NICKNAME_MAX) return `昵称最多 ${NICKNAME_MAX} 个字`
  return null
}

export const cleanNickname = normalize
