/** 空状态（原型 03 第 6 屏）：一格还没画的分镜 + 一句话 + 一个按钮。各处空状态共用，只换文案 */

import { Text, View } from '@tarojs/components'

import { Btn } from './ui'

interface EmptyProps {
  frame: string
  title: string
  text: string
  action: string
  onAction: () => void
}

export default function Empty({ frame, title, text, action, onAction }: EmptyProps) {
  return (
    <View className='empty'>
      <View className='frame'>{frame}</View>
      <Text className='e-h3'>{title}</Text>
      <Text className='e-p'>{text}</Text>
      <Btn onClick={onAction}>{action}</Btn>
    </View>
  )
}
