/**
 * 自定义底部标签栏（原型 proto.js tabbar：闯关 / 复习 / 我的）。
 * 写法照 Taro 官方 custom-tabbar-react 示例：class 组件 + setSelected；
 * 每个标签页在 useDidShow 里调用 Taro.getTabBar(page)?.setSelected(i)（见 components/TabPage.tsx）；
 * 页面弹窗时用 setHidden 收起（wx.hideTabBar 管不到自定义 tabBar，页面遮罩也盖不住它）。
 * 注意：自定义 tabBar 是独立组件，app.wxss 对它不生效，样式全部写在本目录的 index.scss。
 */

import { Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Component } from 'react'

import { TABS } from '../core/tabs'
import './index.scss'

interface State {
  selected: number
  hidden: boolean
}

export default class CustomTabBar extends Component<object, State> {
  state: State = { selected: 0, hidden: false }

  setSelected(selected: number) {
    this.setState({ selected })
  }

  setHidden(hidden: boolean) {
    this.setState({ hidden })
  }

  switchTab(index: number, url: string) {
    if (index === this.state.selected) return
    this.setSelected(index)
    Taro.switchTab({ url })
  }

  render() {
    const { selected, hidden } = this.state
    return (
      <View className={`tabbar ${hidden ? 'is-hidden' : ''}`}>
        <View className='tabbar-row'>
          {TABS.map((tab, i) => {
            const on = i === selected
            return (
              <View
                key={tab.path}
                className={`tab ${on ? 'is-on' : ''}`}
                onClick={this.switchTab.bind(this, i, tab.path)}
              >
                <View className={`tab-icon tab-${tab.icon}${on ? '-on' : ''}`} />
                <Text className='tab-text'>{tab.text}</Text>
              </View>
            )
          })}
        </View>
      </View>
    )
  }
}
