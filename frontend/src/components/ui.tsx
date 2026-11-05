/** 设计规范里的公共组件（00-style-board.html「核心组件」） */

import { Text, View } from '@tarojs/components'
import { useState, type ReactNode } from 'react'

import { iconClass } from '../assets/icon-class'
import type { IconName } from '../assets/icons'
import type { CellState } from '../core/session'

export function Icon({ name, className = '' }: { name: IconName; className?: string }) {
  // 图标图片在 icons.generated.scss 里，避免内联 style 携带 base64
  return <View className={`icon ${iconClass(name)} ${className}`} />
}

interface BtnProps {
  kind?: 'primary' | 'ghost'
  disabled?: boolean
  className?: string
  onClick?: () => void
  children: ReactNode
}

/** 能按的东西才有右下墨影，按下去影子消失 */
export function Btn({ kind = 'primary', disabled, className = '', onClick, children }: BtnProps) {
  return (
    <View
      className={`btn btn-${kind} ${disabled ? 'is-disabled' : ''} ${className}`}
      hoverClass={disabled ? 'none' : 'btn-pressed'}
      hoverStayTime={80}
      onClick={() => !disabled && onClick?.()}
    >
      {children}
    </View>
  )
}

export function StatChip({ icon, children, className = '' }: { icon: 'xp' | 'coin'; children: ReactNode; className?: string }) {
  return (
    <View className={`chip-stat ${className}`}>
      <Icon name={icon} />
      <Text>{children}</Text>
    </View>
  )
}

export function LvChip({ label, percent }: { label: string; percent: number }) {
  return (
    <View className='lvchip'>
      <Text>{label}</Text>
      <View className='xp'>
        <View className='xp-fill' style={{ width: `${percent}%` }} />
      </View>
    </View>
  )
}

export function Cells({ states }: { states: CellState[] }) {
  return (
    <View className='cells'>
      {states.map((s, i) => (
        <View key={i} className={`cell ${s}`} />
      ))}
    </View>
  )
}

interface CaptionBoxProps {
  /** 答对默认收起，答错默认展开 */
  defaultOpen: boolean
  answerLine?: string
  explanation: string
  knowledgePoint: string
  toggleable?: boolean
}

export function CaptionBox({ defaultOpen, answerLine, explanation, knowledgePoint, toggleable = true }: CaptionBoxProps) {
  const [open, setOpen] = useState(defaultOpen)
  const paragraphs = explanation.split(/\n+/).filter((p) => p.trim())
  return (
    <View className='caption-box'>
      <View className='cb-head'>
        <Text className='cb-title'>讲解</Text>
        {toggleable && (
          <Text className='cb-toggle' onClick={() => setOpen(!open)}>
            {open ? '收起' : '展开'}
          </Text>
        )}
      </View>
      {open && (
        <View className='cb-body'>
          {answerLine && <Text className='p answer'>{answerLine}</Text>}
          {paragraphs.map((p, i) => (
            <Text key={i} className='p'>
              {p.trim()}
            </Text>
          ))}
          <Text className='kp'>知识点：{knowledgePoint}</Text>
        </View>
      )}
    </View>
  )
}

/** 拟声词爆炸框：“叮！”（proto.js data-burst="16,56,36"） */
export function Burst({ text, className = '' }: { text: string; className?: string }) {
  return (
    <View className={`burst ${className}`}>
      <View className='burst-bg icon img-burst' />
      <Text className='sfx'>{text}</Text>
    </View>
  )
}

interface DialogProps {
  title: string
  text: string
  primary: string
  ghost: string
  onPrimary: () => void
  onGhost: () => void
}

export function Dialog({ title, text, primary, ghost, onPrimary, onGhost }: DialogProps) {
  return (
    <View className='scrim' catchMove>
      <View className='dialog'>
        <Text className='d-title'>{title}</Text>
        <Text className='d-text'>{text}</Text>
        <View className='row'>
          <Btn onClick={onPrimary}>{primary}</Btn>
          <Btn kind='ghost' onClick={onGhost}>
            {ghost}
          </Btn>
        </View>
      </View>
    </View>
  )
}

export function Toast({ text }: { text: string }) {
  return (
    <View className='toast'>
      <Icon name='ok' />
      <Text>{text}</Text>
    </View>
  )
}

/** 底部安全区占位（透明）。有底栏的页面放进底栏里，让底栏的颜色铺满安全区 */
export function SafeBottom() {
  return <View className='safe-bottom' />
}
