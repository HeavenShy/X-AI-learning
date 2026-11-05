/** 底部标签（原型：闯关 / 复习 / 我的）。顺序即 setSelected 的下标 */
export const TABS = [
  { path: '/pages/index/index', text: '闯关', icon: 'quest' },
  { path: '/pages/review/index', text: '复习', icon: 'review' },
  { path: '/pages/me/index', text: '我的', icon: 'me' }
] as const

export const TAB_INDEX = { quest: 0, review: 1, me: 2 } as const
