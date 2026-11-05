/**
 * 选项作答与判题后展示：闯关页、重做错题页共用（原型 01 第 8–13 屏）。
 * 单选、判断点一下就提交；多选点选项只切换选中，由页面底部按钮提交。
 * 判题动画由页面根节点的 anim 类触发（app.scss「判题动画」），这里只给出 is-<状态> 与 m<顺序>。
 */

import { Text, View } from '@tarojs/components'

import { optionVisual, type JudgeResult } from '../core/judge'
import type { Question } from '../types/api'
import './question-options.scss'

export function Mark({ ok }: { ok: boolean }) {
  return <View className={`mark icon ${ok ? 'icon-mark-ok' : 'icon-mark-no'}`} />
}

const judgeSub = (key: string) => (key === 'A' ? '这个说法正确' : '这个说法不对')

export function AnsweredOptions({ q, r }: { q: Question; r: JudgeResult }) {
  if (q.type === 'judge') {
    return (
      <View className='judge'>
        {q.options.map((o) => {
          const v = optionVisual(q, r, o.key)
          return (
            <View key={o.key} className={`judge-btn is-${v.state} m${v.order}`}>
              <Text className='judge-b'>{o.text}</Text>
              <Text className='judge-s'>{judgeSub(o.key)}</Text>
              {(v.state === 'right' || v.state === 'wrong') && <Mark ok={v.state === 'right'} />}
            </View>
          )
        })}
      </View>
    )
  }
  return (
    <View className='opts'>
      {q.options.map((o) => {
        const v = optionVisual(q, r, o.key)
        return (
          <View key={o.key} className={`opt is-${v.state} m${v.order}`}>
            <Text className='key'>{o.key}</Text>
            <Text>{o.text}</Text>
            {(v.state === 'right' || v.state === 'wrong') && <Mark ok={v.state === 'right'} />}
            {v.state === 'missed' && <Text className='miss-tag'>漏选</Text>}
          </View>
        )
      })}
    </View>
  )
}

interface Props {
  q: Question
  /** 判题结果；null 表示还没作答 */
  result: JudgeResult | null
  /** 多选题当前选中的选项 */
  picked: string[]
  /** 多选题点选项：切换选中 */
  onToggle: (key: string) => void
  /** 单选、判断点一下即提交 */
  onSubmit: (selected: string[]) => void
}

export default function QuestionOptions({ q, result, picked, onToggle, onSubmit }: Props) {
  if (result) return <AnsweredOptions q={q} r={result} />
  if (q.type === 'judge') {
    return (
      <View className='judge'>
        {q.options.map((o) => (
          <View key={o.key} className='judge-btn' hoverClass='judge-pressed' onClick={() => onSubmit([o.key])}>
            <Text className='judge-b'>{o.text}</Text>
            <Text className='judge-s'>{judgeSub(o.key)}</Text>
          </View>
        ))}
      </View>
    )
  }
  return (
    <View className='opts'>
      {q.options.map((o) => {
        const on = picked.includes(o.key)
        return (
          <View
            key={o.key}
            className={`opt ${on ? 'is-picked' : ''}`}
            onClick={() => (q.type === 'single' ? onSubmit([o.key]) : onToggle(o.key))}
          >
            <Text className='key'>{o.key}</Text>
            <Text>{o.text}</Text>
          </View>
        )
      })}
    </View>
  )
}
