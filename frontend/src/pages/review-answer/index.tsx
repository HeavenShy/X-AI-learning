/**
 * 重做错题（原型 03 第 9 屏“错题详情”的作答版）：从复习页点开一道错题进入。
 * 作答交互与闯关页一致（单选、判断点一下即判；多选选好后提交），判题动画用本地结果；
 * 是否移出错题本以服务端返回的 mastered 为准。重做不发经验金币。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import NavBar from '../../components/NavBar'
import QuestionOptions from '../../components/QuestionOptions'
import { Btn, Burst, CaptionBox, SafeBottom } from '../../components/ui'
import { TYPE_LABEL } from '../../core/format'
import { answerLine, judgeAnswer, resultTitle, type JudgeResult } from '../../core/judge'
import { lastAnswerText, wrongCountLabel } from '../../core/review'
import { submitReviewAnswer } from '../../services/api'
import { useStore } from '../../store'
import type { Question } from '../../types/api'
import './index.scss'

const HINT: Record<Question['type'], string> = {
  single: '点一下选项就会判对错。',
  judge: '点一下就会判对错。',
  multiple: '多选题，可以选多个，选好后点提交。'
}

type Save = 'saving' | 'saved' | 'failed'

const REVIEW_URL = '/pages/review/index'

function backToReview() {
  if (Taro.getCurrentPages().length > 1) Taro.navigateBack()
  else Taro.switchTab({ url: REVIEW_URL })
}

export default function ReviewAnswer() {
  const item = useStore((s) => s.reviewing)
  const setReviewMastered = useStore((s) => s.setReviewMastered)
  /** 第几次作答：“再做一次”时加一，用来重置滚动位置与讲解展开状态 */
  const [attempt, setAttempt] = useState(0)
  const [picked, setPicked] = useState<string[]>([])
  const [result, setResult] = useState<JudgeResult | null>(null)
  const [animate, setAnimate] = useState(false)
  const [save, setSave] = useState<Save | null>(null)
  const [mastered, setMastered] = useState(false)
  /** 本页里累计的答错次数（重做答错并保存成功后加一） */
  const [wrongCount, setWrongCount] = useState(item?.wrong_count ?? 0)
  /** “上次的答案”：本次作答期间仍显示之前那次，点“再做一次”后才换成刚保存的错误答案 */
  const [lastSelected, setLastSelected] = useState<string[]>(item?.last_selected_answers ?? [])
  const [savedWrong, setSavedWrong] = useState<string[] | null>(null)
  const [barHeight, setBarHeight] = useState(0)
  /** 本次作答已提交（防止重新渲染前连点两下提交两次） */
  const answered = useRef(false)

  // 被系统回收后重进等情况拿不到要重做的题：回复习页（同闯关页用 reLaunch，顺带清掉页面栈）
  useEffect(() => {
    if (!item) Taro.reLaunch({ url: REVIEW_URL })
  }, [item])

  useEffect(() => {
    if (!result) {
      setBarHeight(0)
      return
    }
    // 结果条盖在页面底部，内容区末尾垫同样的高度，讲解才能滚到它上方（同闯关页）
    Taro.nextTick(() => {
      Taro.createSelectorQuery()
        .select('.result-bar')
        .boundingClientRect((rect) => {
          const r = Array.isArray(rect) ? rect[0] : rect
          if (r?.height) setBarHeight(r.height)
        })
        .exec()
    })
  }, [result, save])

  if (!item) return <View className='screen' />
  const q = item.question

  const submit = async (selected: string[]) => {
    if (answered.current || selected.length === 0) return
    answered.current = true
    const local = judgeAnswer(q, selected)
    setResult(local)
    setAnimate(true)
    setSave('saving')
    try {
      const res = await submitReviewAnswer({
        quiz_id: item.quiz_id,
        question_id: q.id,
        selected_answers: local.picked
      }).promise
      setMastered(res.mastered)
      if (res.mastered) setReviewMastered({ quiz_id: item.quiz_id, question_id: q.id })
      else if (!res.is_correct) {
        setWrongCount((n) => n + 1)
        setSavedWrong(local.picked)
      }
      setSave('saved')
    } catch (e) {
      console.warn('[review-answer] 保存失败', e)
      setSave('failed')
      Taro.showToast({ title: '没保存上，稍后再试', icon: 'none' })
    }
  }

  const togglePick = (key: string) => {
    setPicked((p) => (p.includes(key) ? p.filter((k) => k !== key) : [...p, key]))
  }

  const retry = () => {
    answered.current = false
    if (savedWrong) setLastSelected(savedWrong)
    setSavedWrong(null)
    setAttempt((n) => n + 1)
    setPicked([])
    setResult(null)
    setAnimate(false)
    setSave(null)
  }

  const subline = () => {
    if (save === 'saving') return '正在保存…'
    if (save === 'failed') return '没保存上，这题还在错题本里，稍后再试。'
    if (mastered) return '已移出错题本。'
    return `还在错题本里，${wrongCountLabel(wrongCount)}。看完讲解再做一次。`
  }

  return (
    <View className={`screen review-answer ${animate ? 'anim' : ''}`}>
      <NavBar variant='title' title='重做错题' left='back' onLeft={backToReview} />
      <ScrollView scrollY className='scroll' key={attempt}>
        <View className='scroll-inner ra-inner'>
          <Text className='ra-from'>
            {item.quiz_title} · {wrongCountLabel(wrongCount)}
          </Text>

          <View className='q-panel'>
            <Text className='tag'>{TYPE_LABEL[q.type]}题</Text>
            <Text className='stem'>{q.stem}</Text>
            {result &&
              (result.isCorrect ? (
                <Burst text='叮！' className='sfx-pop q-burst' />
              ) : (
                <Text className='sfx is-gloom sfx-pop q-boom'>嘭！</Text>
              ))}
          </View>

          <QuestionOptions q={q} result={result} picked={picked} onToggle={togglePick} onSubmit={(s) => void submit(s)} />

          {!result && <Text className='q-hint'>{HINT[q.type]}</Text>}
          <Text className='ra-last'>{lastAnswerText(q, lastSelected)}</Text>

          {result && (
            <View className='after'>
              <CaptionBox
                key={attempt}
                defaultOpen
                answerLine={result.isCorrect ? undefined : answerLine(q)}
                explanation={q.explanation}
                knowledgePoint={q.knowledge_point}
                sources={q.sources}
              />
            </View>
          )}
          <View className='ra-pad' />
          {result && <View className='bar-spacer' style={{ height: `${barHeight}px` }} />}
        </View>
      </ScrollView>

      {!result && q.type === 'multiple' && (
        <View className='q-foot'>
          <Btn disabled={picked.length === 0} onClick={() => void submit(picked)}>
            {picked.length ? `提交答案（已选 ${picked.length} 项）` : '提交答案'}
          </Btn>
          <SafeBottom />
        </View>
      )}

      {result && (
        <View className={`result-bar ${result.isCorrect ? 'is-ok' : ''}`}>
          <Text className='rb-title'>{resultTitle(q, result)}</Text>
          <Text className={`rb-sub ${mastered ? 'is-done' : ''}`}>{subline()}</Text>
          {result.isCorrect && save !== 'failed' ? (
            <Btn onClick={backToReview}>回到复习</Btn>
          ) : (
            <View className='ra-row'>
              <Btn kind='ghost' onClick={backToReview}>
                回到复习
              </Btn>
              <Btn disabled={save === 'saving'} onClick={retry}>
                再做一次
              </Btn>
            </View>
          )}
          <SafeBottom />
        </View>
      )}

      {!result && q.type !== 'multiple' && <SafeBottom />}
    </View>
  )
}
