/**
 * 复盘报告：原型 01 第 15（生成中）、16（完成）屏。
 * - 本次闯关：分数在本地算好立刻显示；三句总结、掌握度、下话预告等报告接口返回后填入（结算页已提前发起）。
 * - 历史回看（?quiz_id=xxx，从“历史记录”进入）：同一套版式，数据来自 /user/quizzes/{quiz_id}；
 *   当时 AI 复盘没写出来的，可以在这里“重试”补上。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import NavBar from '../../components/NavBar'
import { Btn, SafeBottom } from '../../components/ui'
import { formatDuration } from '../../core/format'
import { WEAK_BELOW } from '../../core/mastery'
import { sessionStats } from '../../core/session'
import { generateReport, getQuizDetail } from '../../services/api'
import { ensureReport } from '../../services/report-flow'
import { ApiError } from '../../services/request'
import { useStore } from '../../store'
import type { DifficultyOption, QuestionCount, QuizDetail, Report } from '../../types/api'
import './index.scss'

const NUMS = ['一', '二', '三']

function Placeholder({ short = false }: { short?: boolean }) {
  return <View className={`ph ${short ? 's' : ''}`} />
}

/** 报告页要展示的全部内容，与数据来源（本次会话 / 历史记录）无关 */
interface ReportView {
  title: string
  accuracy: number
  correct: number
  total: number
  durationMs: number
  reward: { xp: number; coins: number } | null
  episode: number
  status: 'loading' | 'done' | 'error'
  data: Report | null
  again: { text: string; count: QuestionCount; difficulty: DifficultyOption }
}

/** 本次闯关 */
function useCurrentView(enabled: boolean): ReportView | null {
  const session = useStore((s) => s.session)
  const report = useStore((s) => s.report)

  useEffect(() => {
    if (!enabled) return
    const s = useStore.getState().session
    if (!s || !s.finished) {
      Taro.reLaunch({ url: '/pages/index/index' })
      return
    }
    ensureReport()
  }, [enabled])

  if (!enabled || !session || !session.finished) return null
  const st = sessionStats(session)
  const current = report && report.quizId === session.quiz.quiz_id ? report : null
  return {
    title: session.quiz.title,
    accuracy: st.accuracy,
    correct: st.correct,
    total: st.total,
    durationMs: st.durationMs,
    reward: session.reward ? { xp: session.reward.xp, coins: session.reward.coins } : null,
    episode: session.reward?.episode ?? 1,
    status: current?.status ?? 'loading',
    data: current?.status === 'done' ? current.data : null,
    again: {
      text: session.quiz.user_input,
      count: session.quiz.questions.length as QuestionCount,
      difficulty: session.difficulty
    }
  }
}

type HistoryState =
  | { phase: 'loading' }
  | { phase: 'failed'; message: string }
  | { phase: 'ready'; detail: QuizDetail; reportStatus: 'loading' | 'done' | 'error' }

/** 历史回看 */
function useHistoryView(quizId: string | undefined) {
  const [state, setState] = useState<HistoryState>({ phase: 'loading' })

  const loadDetail = () => {
    if (!quizId) return
    setState({ phase: 'loading' })
    getQuizDetail(quizId)
      .promise.then((detail) => setState({ phase: 'ready', detail, reportStatus: detail.report ? 'done' : 'error' }))
      .catch((e) =>
        setState({ phase: 'failed', message: e instanceof ApiError ? e.message : '没打开这一话的记录' })
      )
  }

  /** 当时 AI 复盘失败：用存档的题目和答题记录补生成（后端不会重复结算经验） */
  const retryReport = (detail: QuizDetail) => {
    setState({ phase: 'ready', detail, reportStatus: 'loading' })
    generateReport({
      quiz_id: detail.quiz.quiz_id,
      topic: detail.quiz.title,
      questions: detail.quiz.questions,
      answer_records: detail.answer_records
    })
      .promise.then((report) => setState({ phase: 'ready', detail: { ...detail, report }, reportStatus: 'done' }))
      .catch(() => setState({ phase: 'ready', detail, reportStatus: 'error' }))
  }

  useEffect(loadDetail, [quizId])

  let view: ReportView | null = null
  if (state.phase === 'ready') {
    const d = state.detail
    view = {
      title: d.quiz.title,
      accuracy: d.accuracy,
      correct: d.correct_count,
      total: d.total_count,
      durationMs: d.total_duration_ms,
      reward: d.reward,
      episode: d.episode,
      status: state.reportStatus,
      data: state.reportStatus === 'done' ? d.report : null,
      again: { text: d.quiz.user_input, count: d.quiz.questions.length as QuestionCount, difficulty: d.difficulty }
    }
  }
  return { state, view, loadDetail, retry: () => state.phase === 'ready' && retryReport(state.detail) }
}

export default function ReportPage() {
  const quizId = useRouter().params.quiz_id
  const fromHistory = !!quizId
  const currentView = useCurrentView(!fromHistory)
  const history = useHistoryView(quizId)
  const view = fromHistory ? history.view : currentView

  if (fromHistory && history.state.phase !== 'ready') {
    const failed = history.state.phase === 'failed' ? history.state.message : null
    return (
      <View className='screen report'>
        <NavBar variant='title' title='本话完结' left='back' />
        <View className='content'>
          <View className='pn wide'>
            {failed ? (
              <View className='fail-note'>
                <Text className='fail-t'>{failed}</Text>
                <View className='retry' hoverClass='retry-pressed' onClick={history.loadDetail}>
                  重试
                </View>
              </View>
            ) : (
              <View className='wait-note'>
                <View className='dots'>
                  <View className='dot' />
                  <View className='dot' />
                  <View className='dot' />
                </View>
                <Text>正在翻出这一话的复盘</Text>
              </View>
            )}
          </View>
        </View>
      </View>
    )
  }

  if (!view) return <View className='screen' />
  const { data } = view

  const onRetry = () => (fromHistory ? history.retry() : ensureReport(true))

  const onAgain = () => {
    useStore.getState().requestGenerate(view.again)
    Taro.reLaunch({ url: '/pages/generating/index' })
  }

  const onPoster = () => {
    if (!data) return
    useStore.getState().setPoster({
      episode: view.episode,
      title: view.title,
      quote: data.share_quote,
      correct: view.correct,
      total: view.total,
      duration: formatDuration(view.durationMs)
    })
    Taro.navigateTo({ url: '/pages/poster/index' })
  }

  return (
    <View className='screen report'>
      <NavBar variant='title' title='本话完结' left='back' />
      <ScrollView scrollY className='scroll'>
        <View className='scroll-inner'>
          <View className='page'>
            <View className='pn wide score-pn'>
              <Text className='num'>
                {view.accuracy}
                <Text className='num-s'>分</Text>
              </Text>
              <View className='t'>
                <Text className='t-b'>{view.title}</Text>
                <Text>
                  答对 {view.correct} 题，共 {view.total} 题，用时 {formatDuration(view.durationMs)}
                </Text>
                {view.reward && (
                  <Text>
                    获得 {view.reward.xp} 经验、{view.reward.coins} 金币
                  </Text>
                )}
              </View>
            </View>

            {!data && (
              <View className='pn wide'>
                {view.status === 'error' ? (
                  <View className='fail-note'>
                    <Text className='fail-t'>复盘没写出来，可能是网络不稳。</Text>
                    <View className='retry' hoverClass='retry-pressed' onClick={onRetry}>
                      重试
                    </View>
                  </View>
                ) : (
                  <View className='wait-note'>
                    <View className='dots'>
                      <View className='dot' />
                      <View className='dot' />
                      <View className='dot' />
                    </View>
                    <Text>AI 正在根据你的答题情况写复盘，约 10 秒</Text>
                  </View>
                )}
              </View>
            )}
            {data && (
              <View className='pn wide pn-h'>
                <Text className='h5'>三格记住它</Text>
              </View>
            )}

            <View className='strips'>
              {NUMS.map((n, i) => (
                <View key={n} className='pn strip'>
                  <Text className='em'>{n}</Text>
                  {data ? (
                    <Text>{data.three_line_summary[i]}</Text>
                  ) : (
                    <>
                      <Placeholder />
                      <Placeholder />
                      <Placeholder short />
                    </>
                  )}
                </View>
              ))}
            </View>

            <View className='pn wide'>
              <Text className='h5'>掌握度</Text>
              {data ? (
                <View className='kps'>
                  {data.knowledge_mastery.map((m) => (
                    <View key={m.point} className={`kp-li ${m.accuracy < WEAK_BELOW ? 'weak' : ''}`}>
                      <Text className='kp-name'>{m.point}</Text>
                      <View className='meter'>
                        <View className='meter-i' style={{ width: `${m.accuracy}%` }} />
                      </View>
                      <Text className='pct'>{m.accuracy}%</Text>
                    </View>
                  ))}
                </View>
              ) : (
                <>
                  <Placeholder />
                  <Placeholder />
                  <Placeholder short />
                </>
              )}
            </View>

            <View className='pn wide'>
              <Text className='h5'>下话预告</Text>
              {data ? (
                <View className='next'>
                  {data.advice.map((a) => (
                    <Text key={a} className='next-li'>
                      {a}
                    </Text>
                  ))}
                </View>
              ) : (
                <>
                  <Placeholder />
                  <Placeholder short />
                </>
              )}
            </View>
          </View>
          <View className='report-pad' />
        </View>
      </ScrollView>
      <View className='report-foot'>
        <View className='report-actions'>
          <Btn className='ra-primary' disabled={!data} onClick={onPoster}>
            生成分享海报
          </Btn>
          <Btn kind='ghost' className='ra-ghost' onClick={onAgain}>
            再闯一轮
          </Btn>
        </View>
        <SafeBottom />
      </View>
    </View>
  )
}
