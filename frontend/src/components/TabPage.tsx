/** 标签页公共逻辑：显示时同步标签栏选中态；页面底部给固定定位的标签栏留出位置 */

import { View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'

interface TabBarInstance {
  setSelected: (i: number) => void
  setHidden: (hidden: boolean) => void
}

const currentTabBar = () => Taro.getTabBar<TabBarInstance>(Taro.getCurrentInstance().page)

export function useTabSelected(index: number) {
  useDidShow(() => currentTabBar()?.setSelected(index))
}

/** 页面弹窗时收起 / 恢复标签栏 */
export function setTabBarHidden(hidden: boolean) {
  currentTabBar()?.setHidden(hidden)
}

/** 与 custom-tab-bar 等高（58px + 2.5px 上边框 + 底部安全区） */
export function TabBarSpace() {
  return <View className='tabbar-space' />
}
