/**
 * 闯关页：原型 01 第 8–13 屏。
 * 单选、判断点一下就判；多选选好后提交。答对加经验、讲解默认收起；答错不加、讲解默认展开。
 * 判题动画顺序同原型：先标错 → 再标对 → 再提示漏选 → 拟声词 → 结果条。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import NavBar, { goBackOrHome } from '../../components/NavBar'
import QuestionOptions from '../../components/QuestionOptions'
import { Btn, Burst, CaptionBox, Cells, Dialog, SafeBottom, StatChip } from '../../components/ui'
import { TYPE_LABEL } from '../../core/format'
import { answerLine, judgeAnswer, resultTitle } from '../../core/judge'
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

export default function QuizPage() {
  const session = useStore((s) => s.session)
  const answer = useStore((s) => s.answer)
  const next = useStore((s) => s.next)
  const [picked, setPicked] = useState<string[]>([])
  const [animate, setAnimate] = useState(false)
  const [showExit, setShowExit] = useState(false)
  /** 结果条盖在页面底部，内容区末尾垫同样的高度，讲解才能滚到它上方 */
  const [barHeight, setBarHeight] = useState(0)
  const shownAt = useRef(Date.now())

  const live = session && !session.finished ? session : null
  const qid = live ? currentQuestion(live).id : ''
  const answered = !!(live && currentAnswer(live))
  useEffect(() => {
    shownAt.current = Date.now()
    setPicked([])
    setAnimate(false)
  }, [qid])

  useEffect(() => {
    if (!answered) {
      setBarHeight(0)
      return
    }
    // 结果条的高度随标题换行变化，渲染后量一次（transform 不影响高度，动画中量也准）
    Taro.nextTick(() => {
      Taro.createSelectorQuery()
        .select('.result-bar')
        .boundingClientRect((rect) => {
          const r = Array.isArray(rect) ? rect[0] : rect
          if (r?.height) setBarHeight(r.height)
        })
        .exec()
    })
  }, [qid, answered])

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

          <QuestionOptions q={q} result={result} picked={picked} onToggle={togglePick} onSubmit={submit} />

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
          {result && <View className='bar-spacer' style={{ height: `${barHeight}px` }} />}
        </View>
      </ScrollView>

      {!result && q.type === 'multiple' && (
        <View className='q-foot'>
          <Btn disabled={picked.length === 0} onClick={() => submit(picked)}>
            {picked.length ? `提交答案（已选 ${picked.length} 项）` : '提交答案'}
          </Btn>
          <SafeBottom />
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
          <SafeBottom />
        </View>
      )}

      {/* 底栏自带安全区；没有底栏时由页面底色让出安全区 */}
      {!result && q.type !== 'multiple' && <SafeBottom />}

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
