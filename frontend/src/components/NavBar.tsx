/**
 * 自定义导航栏：高度按微信胶囊按钮位置计算，右侧给胶囊留位（胶囊是原生的，不用画）。
 */

import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'

import { Icon } from './ui'

interface Metrics {
  statusBar: number
  navHeight: number
  sidePadding: number
}

let cached: Metrics | null = null

export function navMetrics(): Metrics {
  if (cached) return cached
  let statusBar = 20
  let navHeight = 44
  let sidePadding = 112
  try {
    const win = Taro.getWindowInfo()
    statusBar = win.statusBarHeight || 0
    // 胶囊按钮只有小程序有；H5 上该 API 是 temporarilyNotSupport，会产生未处理的 rejection
    const menu = process.env.TARO_ENV === 'weapp' ? Taro.getMenuButtonBoundingClientRect() : null
    if (menu && menu.height) {
      navHeight = (menu.top - statusBar) * 2 + menu.height
      sidePadding = win.windowWidth - menu.left + 8
    }
  } catch {
    // H5 等环境没有胶囊，使用默认值
  }
  cached = { statusBar, navHeight, sidePadding }
  return cached
}

export function goBackOrHome() {
  if (Taro.getCurrentPages().length > 1) Taro.navigateBack()
  else Taro.reLaunch({ url: '/pages/index/index' })
}

interface NavBarProps {
  /** brand：左侧品牌字（默认“一话一懂”，可用 title 换成“复习”等）；title：居中标题；blank：只占位 */
  variant?: 'brand' | 'title' | 'blank'
  title?: string
  left?: 'back' | 'close' | 'none'
  onLeft?: () => void
  dark?: boolean
  className?: string
}

export default function NavBar({ variant = 'blank', title, left = 'none', onLeft, dark, className = '' }: NavBarProps) {
  const m = navMetrics()
  const centered = variant === 'title'
  return (
    <View className={`navbar-wrap ${className}`} style={{ paddingTop: `${m.statusBar}px` }}>
      <View
        className={`navbar ${centered ? 'is-center' : ''}`}
        style={{
          height: `${m.navHeight}px`,
          paddingRight: `${m.sidePadding}px`,
          paddingLeft: centered ? `${m.sidePadding}px` : undefined
        }}
      >
        {left !== 'none' && (
          <View className='back' onClick={onLeft ?? goBackOrHome}>
            {left === 'close' ? (
              <Icon name='close' className='ic-close' />
            ) : (
              <Icon name={dark ? 'backWhite' : 'back'} className='ic-back' />
            )}
          </View>
        )}
        {variant === 'brand' && <Text className='brand'>{title ?? '一话一懂'}</Text>}
        {variant === 'title' && <Text className={`title ${dark ? 'is-dark' : ''}`}>{title}</Text>}
      </View>
    </View>
  )
}
