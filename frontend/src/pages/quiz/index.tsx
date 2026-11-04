/**
 * 闯关页：原型 01 第 8–13 屏。
 * 单选、判断点一下就判；多选选好后提交。答对加经验、讲解默认收起；答错不加、讲解默认展开。
 * 判题动画顺序同原型：先标错 → 再标对 → 再提示漏选 → 拟声词 → 结果条。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import NavBar, { goBackOrHome } from '../../components/NavBar'
import { Btn, Burst, CaptionBox, Cells, Dialog, SafeBottom, StatChip } from '../../components/ui'
import { TYPE_LABEL } from '../../core/format'
import { answerLine, judgeAnswer, optionVisual, resultTitle, type JudgeResult } from '../../core/judge'
import { COINS_PER_CORRECT, XP_PER_CORRECT } from '../../core/level'
import { cellStates, currentAnswer, currentQuestion, isLastQuestion, sessionStats } from '../../core/session'
import { useStore } from '../../store'
import type { Question } from '../../types/api'
import './index.scss'

const HINT: Record<Question['type'], string> = {
  single: '点一下选项就会判对错。',
  judge: '点一下就会判对错。',
  multiple: '多选题，可以选多个，选好后点提交。'
}

function Mark({ ok }: { ok: boolean }) {
  return <View className={`mark icon ${ok ? 'icon-mark-ok' : 'icon-mark-no'}`} />
}

function AnsweredOptions({ q, r }: { q: Question; r: JudgeResult }) {
  if (q.type === 'judge') {
    return (
      <View className='judge'>
        {q.options.map((o) => {
          const v = optionVisual(q, r, o.key)
          return (
            <View key={o.key} className={`judge-btn is-${v.state} m${v.order}`}>
              <Text className='judge-b'>{o.text}</Text>
              <Text className='judge-s'>{o.key === 'A' ? '这个说法正确' : '这个说法不对'}</Text>
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

export default function QuizPage() {
  const session = useStore((s) => s.session)
  const answer = useStore((s) => s.answer)
  const next = useStore((s) => s.next)
  const [picked, setPicked] = useState<string[]>([])
  const [animate, setAnimate] = useState(false)
  const [showExit, setShowExit] = useState(false)
  const shownAt = useRef(Date.now())

  const qid = session && !session.finished ? currentQuestion(session).id : ''
  useEffect(() => {
    shownAt.current = Date.now()
    setPicked([])
    setAnimate(false)
  }, [qid])

  useEffect(() => {
    if (!session) Taro.reLaunch({ url: '/pages/index/index' })
    else if (session.finished) Taro.redirectTo({ url: '/pages/clear/index' })
  }, [session])

  if (!session || session.finished) return <View className='screen' />

  const q = currentQuestion(session)
  const index = session.index
  const ans = currentAnswer(session)
  const result = ans ? judgeAnswer(q, ans.selected) : null
  const stats = sessionStats(session)
  const last = isLastQuestion(session)

  const submit = (selected: string[]) => {
    if (ans || selected.length === 0) return
    answer(selected, Date.now() - shownAt.current)
    setAnimate(true)
  }

  const togglePick = (key: string) => {
    setPicked((p) => (p.includes(key) ? p.filter((k) => k !== key) : [...p, key]))
  }

  return (
    <View className={`screen quiz ${animate ? 'anim' : ''}`}>
      <NavBar left='close' onLeft={() => setShowExit(true)} />
      <ScrollView scrollY className='scroll' key={q.id}>
        <View className='scroll-inner quiz-inner'>
          <View className='q-top'>
            <View className='q-l'>
              <Cells states={cellStates(session)} />
              <StatChip icon='xp'>{stats.xp}</StatChip>
            </View>
            <Text className='ep'>第 {index + 1} 格</Text>
          </View>

          <View className='q-panel'>
            <Text className='tag'>{TYPE_LABEL[q.type]}题</Text>
            <Text className='stem'>
              {index + 1}. {q.stem}
            </Text>
            {result &&
              (result.isCorrect ? (
                <Burst text='叮！' className='sfx-pop q-burst' />
              ) : (
                <Text className='sfx is-gloom sfx-pop q-boom'>嘭！</Text>
              ))}
          </View>

          {result ? (
            <AnsweredOptions q={q} r={result} />
          ) : q.type === 'judge' ? (
            <View className='judge'>
              {q.options.map((o) => (
                <View key={o.key} className='judge-btn' hoverClass='judge-pressed' onClick={() => submit([o.key])}>
                  <Text className='judge-b'>{o.text}</Text>
                  <Text className='judge-s'>{o.key === 'A' ? '这个说法正确' : '这个说法不对'}</Text>
                </View>
              ))}
            </View>
          ) : (
            <View className='opts'>
              {q.options.map((o) => {
                const on = picked.includes(o.key)
                return (
                  <View
                    key={o.key}
                    className={`opt ${on ? 'is-picked' : ''}`}
                    onClick={() => (q.type === 'single' ? submit([o.key]) : togglePick(o.key))}
                  >
                    <Text className='key'>{o.key}</Text>
                    <Text>{o.text}</Text>
                  </View>
                )
              })}
            </View>
          )}

          {!result && <Text className='q-hint'>{HINT[q.type]}</Text>}

          {result && (
            <View className='after'>
              <CaptionBox
                key={q.id}
                defaultOpen={!result.isCorrect}
                answerLine={result.isCorrect ? undefined : answerLine(q)}
                explanation={q.explanation}
                knowledgePoint={q.knowledge_point}
              />
            </View>
          )}
          <View className='quiz-pad' />
        </View>
      </ScrollView>

      {!result && q.type === 'multiple' && (
        <View className='q-foot'>
          <Btn disabled={picked.length === 0} onClick={() => submit(picked)}>
            {picked.length ? `提交答案（已选 ${picked.length} 项）` : '提交答案'}
          </Btn>
        </View>
      )}

      {result && (
        <View className={`result-bar ${result.isCorrect ? 'is-ok' : ''}`}>
          <Text className='rb-title'>{resultTitle(q, result)}</Text>
          {result.isCorrect ? (
            <View className='gain'>
              <StatChip icon='xp'>+{XP_PER_CORRECT} 经验</StatChip>
              <StatChip icon='coin'>+{COINS_PER_CORRECT} 金币</StatChip>
            </View>
          ) : (
            <Text className='rb-sub'>这题不加经验值。看完讲解，{last ? '马上就通关了' : '下一格接着来'}。</Text>
          )}
          <Btn onClick={next}>{result.isCorrect ? (last ? '去结算' : '下一格') : last ? '懂了，去结算' : '懂了，下一格'}</Btn>
        </View>
      )}

      <SafeBottom />

      {showExit && (
        <Dialog
          title='现在退出？'
          text={`已答 ${stats.answered} 格。进度会保存，回首页点“继续”就能接着答。`}
          primary='继续答题'
          ghost='退出'
          onPrimary={() => setShowExit(false)}
          onGhost={goBackOrHome}
        />
      )}
    </View>
  )
}
