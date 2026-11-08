/**
 * 出题中 / 出题失败：原型 01 第 5、6 屏。
 * 后端是一次性返回，三步进度按预计时长在前端推进；结果回来时全部完成。
 * 知识库出题（genRequest.kb）调知识库出题接口，步骤换成“读取资料 / 找到相关片段 / 出题并写讲解”；
 * 资料未就绪（4023）或重点不合规（4003）时回到出题设置页提示。
 * 网页出题（genRequest.web）调网页出题接口，步骤是“读取网页 / 判断主题与范围 / 出题并写讲解”；
 * 网页打不开、读不出正文、AI 判断没有可学内容（4030–4033）或不合规（4003）时回到网页出题页提示。
 * 视频出题（genRequest.video）调视频出题接口，步骤是“读取文字稿 / 判断主题与范围 / 出题并写讲解”；
 * 解析结果过期（4040 / 4053）、时间段里没讲话（4054）、没有可学内容（4032）或不合规（4003）时回到视频出题页提示。
 */

import { Text, View } from '@tarojs/components'
import Taro, { useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import NavBar, { goBackOrHome } from '../../components/NavBar'
import { Btn, SafeBottom } from '../../components/ui'
import { displayTopic, formatClock, planText } from '../../core/format'
import { generateKbQuiz, generateQuiz, generateVideoQuiz, generateWebQuiz } from '../../services/api'
import { ApiError, type Pending } from '../../services/request'
import { useStore } from '../../store'
import { ErrorCode, type Quiz } from '../../types/api'
import './index.scss'

/** 各题量的预计耗时（毫秒），来自真模型冒烟的中位数 */
const EXPECTED_MS: Record<number, number> = { 3: 5000, 5: 7000, 10: 11000 }
/** 网页出题多了抓取和范围判断 */
const WEB_EXTRA_MS = 4000
const WEB_ERRORS: number[] = [
  ErrorCode.URL_INVALID,
  ErrorCode.PAGE_UNREACHABLE,
  ErrorCode.PAGE_NO_CONTENT,
  ErrorCode.PAGE_NOT_SUPPORTED,
  ErrorCode.CONTENT_NOT_ALLOWED
]
const VIDEO_ERRORS: number[] = [
  ErrorCode.NOT_FOUND,
  ErrorCode.VIDEO_NOT_READY,
  ErrorCode.VIDEO_RANGE_EMPTY,
  ErrorCode.PAGE_NO_CONTENT,
  ErrorCode.CONTENT_NOT_ALLOWED
]

type Phase = 'running' | 'failed'
type StepState = 'done' | 'doing' | 'wait'

const FAIL_COPY: Record<'ai' | 'network', string> = {
  ai: 'AI 返回的题目不完整，已自动重试 2 次仍未成功。你的输入没有问题，可以直接再试一次。',
  network: '网络好像断了，没连上出题服务。你的输入没有问题，检查网络后再试一次。'
}

export default function Generating() {
  const req = useStore((s) => s.genRequest)
  const [phase, setPhase] = useState<Phase>('running')
  const [failKind, setFailKind] = useState<'ai' | 'network'>('ai')
  const [step, setStep] = useState(0) // 0,1,2 进行中；3 全部完成
  const [attempt, setAttempt] = useState(0)
  const pending = useRef<Pending<Quiz> | null>(null)
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])

  const clearTimers = () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
  }

  useEffect(() => {
    if (!req) {
      Taro.reLaunch({ url: '/pages/index/index' })
      return
    }
    setPhase('running')
    setStep(0)
    const expected = (EXPECTED_MS[req.count] ?? 7000) + (req.web || req.video ? WEB_EXTRA_MS : 0)
    timers.current.push(setTimeout(() => setStep((s) => Math.max(s, 1)), 1200))
    timers.current.push(setTimeout(() => setStep((s) => Math.max(s, 2)), Math.max(2400, expected * 0.45)))

    const p = req.video
      ? generateVideoQuiz({
          job_id: req.video.jobId,
          focus: req.text,
          start_seconds: req.video.startSeconds,
          end_seconds: req.video.endSeconds,
          question_count: req.count,
          difficulty: req.difficulty
        })
      : req.web
      ? generateWebQuiz({ url: req.web.url, focus: req.text, question_count: req.count, difficulty: req.difficulty })
      : req.kb
        ? generateKbQuiz(req.kb.kbId, {
            document_ids: req.kb.documentIds,
            focus: req.text,
            question_count: req.count,
            difficulty: req.difficulty
          })
        : generateQuiz({ user_input: req.text, question_count: req.count, difficulty: req.difficulty })
    pending.current = p
    p.promise
      .then((quiz) => {
        clearTimers()
        setStep(3)
        useStore.getState().setPendingQuiz(quiz)
        setTimeout(() => Taro.redirectTo({ url: '/pages/overview/index' }), 300)
      })
      .catch((err: ApiError) => {
        clearTimers()
        if (err.code === ErrorCode.ABORTED) return
        // 网页：打不开 / 读不出正文 / 没有可学内容 / 不合规，回到网页出题页提示原因和替代方式
        if (req.video && VIDEO_ERRORS.includes(err.code)) {
          useStore.getState().setVideoError({ code: err.code, message: err.message })
          goBackOrHome()
          return
        }
        if (req.web && WEB_ERRORS.includes(err.code)) {
          useStore.getState().setWebError({ code: err.code, message: err.message })
          goBackOrHome()
          return
        }
        // 知识库：资料没准备好 / 重点不合规 / 库被删了，回到出题设置页提示
        if (
          req.kb &&
          (err.code === ErrorCode.NO_READY_DOCUMENTS ||
            err.code === ErrorCode.CONTENT_NOT_ALLOWED ||
            err.code === ErrorCode.NOT_FOUND)
        ) {
          useStore.getState().setKbError(err.message)
          goBackOrHome()
          return
        }
        // 输入类问题回到首页，在输入框下方提示（原型第 4 屏）
        if (err.code === ErrorCode.INPUT_TOO_SHORT || err.code === ErrorCode.CONTENT_NOT_ALLOWED) {
          useStore.getState().setHomeError(err.message)
          goBackOrHome()
          return
        }
        setFailKind(err.code === ErrorCode.NETWORK ? 'network' : 'ai')
        setPhase('failed')
      })
    return () => {
      clearTimers()
      p.abort()
    }
  }, [req, attempt])

  useUnload(() => pending.current?.abort())

  if (!req) return <View className='screen' />

  // 取消后回到首页，输入内容保留（草稿在 store 里）
  const onCancel = () => {
    pending.current?.abort()
    goBackOrHome()
  }

  const stepState = (i: number): StepState => (step > i ? 'done' : step === i ? 'doing' : 'wait')
  const focus = displayTopic(req.text)
  const range =
    req.video && (req.video.startSeconds !== undefined || req.video.endSeconds !== undefined)
      ? `${formatClock(req.video.startSeconds ?? 0)}–${req.video.endSeconds !== undefined ? formatClock(req.video.endSeconds) : '结尾'}`
      : ''
  const steps = req.video
    ? [
        { title: '读取文字稿', sub: range ? `只看 ${range}` : `《${req.video.title.slice(0, 14)}》` },
        { title: '判断主题与范围', sub: focus ? `围绕：${focus.slice(0, 14)}` : '挑出核心片段和知识点' },
        { title: '出题并写讲解', sub: `${planText(req.count)}，标出时间点` }
      ]
    : req.web
    ? [
        { title: '读取网页', sub: `《${req.web.title.slice(0, 14)}》` },
        { title: '判断主题与范围', sub: focus ? `围绕：${focus.slice(0, 14)}` : '挑出核心段落和知识点' },
        { title: '出题并写讲解', sub: `${planText(req.count)}，附原文摘录` }
      ]
    : req.kb
    ? [
        { title: '读取资料', sub: `知识库：${req.kb.kbName.slice(0, 14)}` },
        { title: '找到相关片段', sub: focus ? `围绕：${focus.slice(0, 14)}` : '从资料前中后均匀挑选' },
        { title: '出题并写讲解', sub: `${planText(req.count)}，每题标出处` }
      ]
    : [
        { title: '理解你想学什么', sub: `主题：${focus.slice(0, 14)}` },
        { title: '补充相关知识', sub: '定义、原理、易错点和应用场景' },
        { title: '出题并写讲解', sub: planText(req.count) }
      ]
  const ST_TEXT: Record<StepState, string> = { done: '完成', doing: '进行中', wait: '等待' }

  return (
    <View className='screen gen'>
      <NavBar variant='title' title='出题中' left={phase === 'failed' ? 'back' : 'none'} />
      <View className='content'>
        <View className='gen-quote'>
          {req.video ? (
            <>
              用视频出题：<Text className='gen-quote-b'>{req.video.title}</Text>
              {range ? `（${range}）` : ''}
              {focus ? `，重点：${focus}` : ''}
            </>
          ) : req.web ? (
            <>
              用网页出题：<Text className='gen-quote-b'>{req.web.title}</Text>
              {focus ? `，重点：${focus}` : ''}
            </>
          ) : req.kb ? (
            <>
              用知识库出题：<Text className='gen-quote-b'>{req.kb.kbName}</Text>
              {focus ? `，重点：${focus}` : ''}
            </>
          ) : (
            <>
              你想学：<Text className='gen-quote-b'>{focus}</Text>
            </>
          )}
        </View>

        {phase === 'running' ? (
          <>
            <Text className='gen-h'>正在画这一话的 {req.count} 格</Text>
            <View className='steps'>
              {steps.map((s, i) => {
                const st = stepState(i)
                return (
                  <View key={s.title} className={`step ${st}`}>
                    <Text className='n'>{i + 1}</Text>
                    <View className='step-t'>
                      <Text className='step-title'>{s.title}</Text>
                      <Text className='step-sub'>{s.sub}</Text>
                    </View>
                    <Text className='st'>{ST_TEXT[st]}</Text>
                    {st === 'doing' && (
                      <View className='bar-run'>
                        <View className='bar-run-i' />
                      </View>
                    )}
                  </View>
                )
              })}
            </View>
            <Text className='gen-tip'>一般需要 10–20 秒，请停留在这一页。</Text>
            <View className='gen-foot'>
              <Btn kind='ghost' onClick={onCancel}>
                取消出题
              </Btn>
            </View>
          </>
        ) : (
          <>
            <View className='fail-pn'>
              <Text className='fail-h'>这一话没出成</Text>
              <Text className='fail-p'>{FAIL_COPY[failKind]}</Text>
              <View className='fail-ul'>
                <Text className='fail-li'>网络不稳时也会出现这种情况</Text>
                <Text className='fail-li'>换个更具体的说法，成功率更高</Text>
              </View>
            </View>
            <View className='fail-foot'>
              <Btn onClick={() => setAttempt((a) => a + 1)}>重新出题</Btn>
              <Btn kind='ghost' className='mt14' onClick={() => goBackOrHome()}>
                {req.kb || req.web || req.video ? '改一下设置' : '改一下内容'}
              </Btn>
            </View>
          </>
        )}
      </View>
      <SafeBottom />
    </View>
  )
}
