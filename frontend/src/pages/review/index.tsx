/**
 * 复习（底部第二个标签，原型 03 第 7 屏 pages/review）。
 * 错题本 + 遗忘曲线复习不在本期范围，先用原型的空状态结构占位。
 */

import { View } from '@tarojs/components'
import Taro from '@tarojs/taro'

import Empty from '../../components/Empty'
import NavBar from '../../components/NavBar'
import { TabBarSpace, useTabSelected } from '../../components/TabPage'
import { TAB_INDEX } from '../../core/tabs'

export default function Review() {
  useTabSelected(TAB_INDEX.review)
  return (
    <View className='screen'>
      <NavBar variant='brand' title='复习' />
      <View className='content'>
        <Empty
          frame='复习'
          title='复习功能还在画'
          text='答错的题之后会回到这里，先去闯一话吧。'
          action='去闯关'
          onAction={() => Taro.switchTab({ url: '/pages/index/index' })}
        />
      </View>
      <TabBarSpace />
    </View>
  )
}
