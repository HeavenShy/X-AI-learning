/**
 * 用视频出题：原型 02 第 4（设置）、5（解析进度）、6（解析失败）屏。
 * 来源二选一：选视频文件（微信聊天 / 手机相册，≤200 MB、≤30 分钟）或贴 B 站链接（进页面时读剪贴板）。
 * 上传 / 提交链接后后台解析：读取视频 → 提取音频 → 转文字，每 2 秒轮询一次进度（页面隐藏时暂停）。
 * 解析完成后显示预览（视频名、时长、文字稿字数），可选“只学其中一段”、重点、题量，然后进入出题中页。
 * 出题中页遇到解析结果过期、时间段里没讲话、没有可学内容、不合规时带着原因回到这里。
 */

import { Input, ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter, useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import NavBar from '../../components/NavBar'
import { Btn, Icon, SafeBottom } from '../../components/ui'
import { estimateMinutes, formatClock } from '../../core/format'
import {
  extractBilibiliUrl,
  fileExtension,
  jobSteps,
  precheckVideo,
  readyLine,
  validateRange,
  VIDEO_FIX_COPY,
  VIDEO_FOCUS_MAX,
  videoErrorCopy,
  type VideoFix
} from '../../core/video'
import { getVideoJob, submitVideoLink, uploadVideo } from '../../services/api'
import { ApiError, type Pending } from '../../services/request'
import { useStore } from '../../store'
import { ErrorCode, type QuestionCount, type VideoJob } from '../../types/api'
import './index.scss'

const COUNTS: QuestionCount[] = [3, 5, 10]
const POLL_MS = 2000
const MSG_NOT_BILIBILI = '没认出 B 站链接：粘贴 bilibili.com 或 b23.tv 的链接，或者直接填 BV 号。'
const MSG_H5 = '请在微信里上传视频'

type Mode = 'file' | 'link'
type Phase =
  | { kind: 'pick' }
  | { kind: 'uploading'; percent: number }
  | { kind: 'submitting' }
  | { kind: 'processing'; job: VideoJob }
  | { kind: 'ready'; job: VideoJob }
  | { kind: 'failed'; code: number | null; message: string }

function decodeParam(v: string | undefined): string {
  if (!v) return ''
  try {
    return decodeURIComponent(v)
  } catch {
    return v
  }
}

export default function VideoQuizPage() {
  const initialUrl = decodeParam(useRouter().params.url)
  const [mode, setMode] = useState<Mode>(initialUrl ? 'link' : 'file')
  const [source, setSource] = useState<'upload' | 'bilibili'>(initialUrl ? 'bilibili' : 'upload')
  const [phase, setPhase] = useState<Phase>({ kind: 'pick' })
  const [link, setLink] = useState(initialUrl)
  const [linkError, setLinkError] = useState<string | null>(null)
  const [pickError, setPickError] = useState<string | null>(null)
  const [clipTip, setClipTip] = useState(false)
  const [startText, setStartText] = useState('')
  const [endText, setEndText] = useState('')
  const [focus, setFocus] = useState('')
  const [count, setCount] = useState<QuestionCount>(5)
  const [formError, setFormError] = useState<string | null>(null)

  const pending = useRef<Pending<unknown> | null>(null)
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const jobId = useRef<string | null>(null)
  const visible = useRef(true)
  const linkRef = useRef(initialUrl)
  // useDidShow 里要读当前阶段：用 ref，避免拿到旧的 state
  const phaseKind = useRef<Phase['kind']>('pick')
  phaseKind.current = phase.kind

  const stopPolling = () => {
    if (pollTimer.current) clearTimeout(pollTimer.current)
    pollTimer.current = null
  }

  const fail = (e: unknown) => {
    const err = e instanceof ApiError ? e : null
    if (err?.code === ErrorCode.ABORTED) return
    setPhase({ kind: 'failed', code: err ? err.code : null, message: err ? err.message : '' })
  }

  /** 拉一次任务状态；还在处理就 2 秒后再拉（页面隐藏时不排下一次，回来再接上） */
  const poll = () => {
    stopPolling()
    const id = jobId.current
    if (!id || !visible.current) return
    const p = getVideoJob(id)
    pending.current = p
    p.promise
      .then((job) => {
        if (jobId.current !== job.job_id) return
        if (job.status === 'processing') {
          setPhase({ kind: 'processing', job })
          pollTimer.current = setTimeout(poll, POLL_MS)
        } else if (job.status === 'ready') {
          setPhase({ kind: 'ready', job })
        } else {
          setPhase({ kind: 'failed', code: null, message: job.fail_reason ?? '' })
        }
      })
      .catch((e: ApiError) => {
        if (e.code === ErrorCode.NETWORK) {
          // 轮询偶尔断网不算失败，稍后再试
          pollTimer.current = setTimeout(poll, POLL_MS * 2)
          return
        }
        fail(e)
      })
  }

  const track = (job: VideoJob) => {
    jobId.current = job.job_id
    setPhase(job.status === 'ready' ? { kind: 'ready', job } : { kind: 'processing', job })
    if (job.status === 'processing') pollTimer.current = setTimeout(poll, POLL_MS)
  }

  const reset = (nextMode: Mode = mode) => {
    stopPolling()
    pending.current?.abort()
    jobId.current = null
    setMode(nextMode)
    setPhase({ kind: 'pick' })
    setPickError(null)
    setLinkError(null)
    setFormError(null)
    setStartText('')
    setEndText('')
  }

  const submitLink = (raw: string) => {
    const url = extractBilibiliUrl(raw)
    if (!url) {
      setLinkError(raw.trim() ? MSG_NOT_BILIBILI : null)
      return
    }
    setLinkError(null)
    setSource('bilibili')
    setPhase({ kind: 'submitting' })
    const p = submitVideoLink(url)
    pending.current = p
    p.promise.then(track).catch(fail)
  }

  const pickFile = async () => {
    setPickError(null)
    if (process.env.TARO_ENV !== 'weapp') {
      Taro.showToast({ title: MSG_H5, icon: 'none' })
      return
    }
    let tapIndex: number
    try {
      tapIndex = (await Taro.showActionSheet({ itemList: ['从微信聊天里选', '从手机相册选'] })).tapIndex
    } catch {
      return // 取消
    }
    let picked: { path: string; size: number; duration?: number; name: string }
    try {
      if (tapIndex === 0) {
        const res = await Taro.chooseMessageFile({ count: 1, type: 'video' })
        const f = res.tempFiles[0]
        if (!f) return
        picked = { path: f.path, size: f.size, name: f.name || `聊天里的视频.${fileExtension(f.path) || 'mp4'}` }
      } else {
        const res = await Taro.chooseMedia({ count: 1, mediaType: ['video'], sourceType: ['album'] })
        const f = res.tempFiles[0]
        if (!f) return
        picked = {
          path: f.tempFilePath,
          size: f.size,
          duration: f.duration,
          name: `相册里的视频.${fileExtension(f.tempFilePath) || 'mp4'}`
        }
      }
    } catch {
      return // 取消选择
    }
    const err = precheckVideo(picked)
    if (err) {
      setPickError(err)
      return
    }
    setSource('upload')
    setPhase({ kind: 'uploading', percent: 0 })
    const p = uploadVideo(picked.path, picked.name, (percent) =>
      setPhase((cur) => (cur.kind === 'uploading' ? { kind: 'uploading', percent } : cur))
    )
    pending.current = p
    p.promise.then(track).catch(fail)
  }

  // 进页面：带了链接（首页 / 报告页“再来一话”）就直接读；否则看剪贴板里有没有 B 站链接（只填好，不自动读）
  useEffect(() => {
    if (initialUrl) {
      submitLink(initialUrl)
      return
    }
    Taro.getClipboardData()
      .then((res) => {
        const found = extractBilibiliUrl(res.data || '')
        if (found && !linkRef.current) {
          linkRef.current = found
          setLink(found)
          setMode('link')
          setClipTip(true)
        }
      })
      .catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useDidShow(() => {
    visible.current = true
    // 从出题中页带回来的错误
    const { videoError, setVideoError } = useStore.getState()
    if (videoError) {
      setVideoError(null)
      if (videoError.code === ErrorCode.NOT_FOUND || videoError.code === ErrorCode.VIDEO_NOT_READY) {
        jobId.current = null
        setPhase({ kind: 'failed', code: videoError.code, message: videoError.message })
      } else {
        setFormError(videoError.message)
      }
    }
    if (phaseKind.current === 'processing') poll()
  })

  useDidHide(() => {
    visible.current = false
    stopPolling()
  })

  useUnload(() => {
    visible.current = false
    stopPolling()
    pending.current?.abort()
  })

  const onFix = (fix: VideoFix) => {
    if (fix === 'paste') Taro.switchTab({ url: '/pages/index/index' })
    else if (fix === 'upload') {
      reset('file')
      void pickFile()
    } else if (source === 'bilibili' && link) {
      reset('link')
      submitLink(link)
    } else reset()
  }

  const job = phase.kind === 'ready' ? phase.job : null
  const range = job ? validateRange(startText, endText, job.duration_seconds) : {}

  const onStart = () => {
    if (!job) return
    if (range.error) {
      setFormError(range.error)
      return
    }
    useStore.getState().requestGenerate({
      text: focus.trim(),
      count,
      difficulty: 'mixed',
      video: { jobId: job.job_id, title: job.title, startSeconds: range.start, endSeconds: range.end }
    })
    Taro.navigateTo({ url: '/pages/generating/index' })
  }

  const busy = phase.kind === 'uploading' || phase.kind === 'submitting' || phase.kind === 'processing'

  const renderSource = () => (
    <>
      <View className='vq-seg'>
        {(['file', 'link'] as Mode[]).map((m) => (
          <View
            key={m}
            className={`vq-seg-btn ${mode === m ? 'is-on' : ''}`}
            onClick={() => {
              if (mode !== m) {
                setMode(m)
                setPickError(null)
                setLinkError(null)
              }
            }}
          >
            <Text>{m === 'file' ? '选视频文件' : '贴 B 站链接'}</Text>
          </View>
        ))}
      </View>
      {mode === 'file' ? (
        <>
          <View className='vq-pick' hoverClass='vq-pick-pressed' onClick={() => void pickFile()}>
            <View className='vq-pick-i'>
              <Icon name='videoInk' />
            </View>
            <View className='vq-pick-t'>
              <Text className='vq-pick-title'>选一个视频</Text>
              <Text className='vq-small'>从微信聊天或手机相册里选，200 MB、30 分钟以内</Text>
            </View>
            <Text className='vq-chev'>›</Text>
          </View>
          {pickError && (
            <View className='vq-err'>
              <Icon name='warn' />
              <Text>{pickError}</Text>
            </View>
          )}
          <Text className='vq-tip'>视频号、B 站等 App 里的视频，可以先保存到手机再从相册选。只按讲话内容出题，不看画面。</Text>
        </>
      ) : (
        <>
          <View className={`vq-input ${linkError ? 'is-error' : ''}`}>
            <Icon name='linkInk' className='vq-input-i' />
            <Input
              className='vq-input-el'
              value={link}
              type='text'
              confirmType='go'
              maxlength={2000}
              placeholder='粘贴 B 站视频链接或 BV 号'
              placeholderClass='vq-placeholder'
              onInput={(e) => {
                linkRef.current = e.detail.value
                setLink(e.detail.value)
                setClipTip(false)
                if (linkError) setLinkError(null)
              }}
              onConfirm={() => submitLink(linkRef.current)}
            />
          </View>
          {clipTip && (
            <View className='vq-clip'>
              <Icon name='ok' />
              <Text>检测到剪贴板里有 B 站链接，已帮你填好。</Text>
            </View>
          )}
          {linkError && (
            <View className='vq-err'>
              <Icon name='warn' />
              <Text>{linkError}</Text>
            </View>
          )}
          <Text className='vq-tip'>
            有字幕的视频直接用字幕，没有字幕会把讲话转成文字。要登录、会员或有版权限制的视频读不了，可以改为上传。
          </Text>
        </>
      )}
    </>
  )

  const renderProgress = () => {
    const current = phase.kind === 'processing' ? phase.job : null
    const percent = phase.kind === 'uploading' ? phase.percent : 0
    const steps = jobSteps(source, current, percent)
    const ST: Record<string, string> = { done: '完成', doing: '进行中', wait: '等待' }
    return (
      <>
        <View className='vq-card'>
          <View className='vq-card-h'>
            <Text className='vq-card-t'>{current ? current.title : source === 'upload' ? '正在上传视频' : '正在读取 B 站视频'}</Text>
            <Text className='pill run'>解析中</Text>
          </View>
          {current && current.duration_seconds > 0 && (
            <Text className='vq-small'>时长 {formatClock(current.duration_seconds)}</Text>
          )}
        </View>
        <View className='vq-steps'>
          {steps.map((s, i) => (
            <View key={s.title} className={`vq-step ${s.state}`}>
              <Text className='n'>{i + 1}</Text>
              <View className='vq-step-t'>
                <Text className='vq-step-title'>{s.title}</Text>
                <Text className='vq-step-sub'>{s.sub}</Text>
              </View>
              <Text className='st'>{ST[s.state]}</Text>
              {s.state === 'doing' && i === 0 && phase.kind === 'uploading' ? (
                <View className='vq-bar'>
                  <View className='vq-bar-i' style={{ width: `${Math.max(4, percent)}%` }} />
                </View>
              ) : s.state === 'doing' && current && current.progress_total > 0 && i === 2 ? (
                <View className='vq-bar'>
                  <View
                    className='vq-bar-i'
                    style={{ width: `${Math.max(4, (current.progress_done / current.progress_total) * 100)}%` }}
                  />
                </View>
              ) : s.state === 'doing' ? (
                <View className='vq-bar'>
                  <View className='vq-bar-run' />
                </View>
              ) : null}
            </View>
          ))}
        </View>
        <Text className='vq-tip'>10 分钟的视频一般要半分钟左右。可以留在这一页，处理完会自动显示。</Text>
      </>
    )
  }

  const renderFailed = (p: Extract<Phase, { kind: 'failed' }>) => {
    const copy = videoErrorCopy(p.code, p.message, source)
    return (
      <View className='vq-card is-error'>
        <Text className='vq-fail-h'>{copy.title}</Text>
        <Text className='vq-fail-p'>{copy.text}</Text>
        {copy.fixes.length > 0 && (
          <View className='vq-fixes'>
            {copy.fixes.map((f) => (
              <View key={f} className='vq-fix' hoverClass='vq-fix-pressed' onClick={() => onFix(f)}>
                <View className='vq-fix-t'>
                  <Text className='vq-fix-title'>{VIDEO_FIX_COPY[f].title}</Text>
                  <Text className='vq-small'>{VIDEO_FIX_COPY[f].sub}</Text>
                </View>
                <Text className='vq-chev'>›</Text>
              </View>
            ))}
          </View>
        )}
      </View>
    )
  }

  const renderReady = (j: VideoJob) => (
    <>
      <View className='vq-card'>
        <View className='vq-card-h'>
          <Text className='vq-card-t'>视频预览</Text>
          <Text className='pill ok'>{j.via === 'subtitle' ? '已读取字幕' : '已转成文字'}</Text>
        </View>
        <View className='vq-preview'>
          <View className='vq-thumb'>
            <Icon name='videoInk' />
          </View>
          <View className='vq-meta'>
            <Text className='vq-site'>{j.source === 'bilibili' ? 'bilibili.com' : '上传的视频'}</Text>
            <Text className='vq-title'>{j.title}</Text>
            <Text className='vq-small'>{readyLine(j)}</Text>
          </View>
        </View>
      </View>

      <View className='field'>
        <Text className='field-t'>只学其中一段（选填）</Text>
        <View className='vq-range'>
          <View className={`vq-input vq-range-in ${range.error ? 'is-error' : ''}`}>
            <Input
              className='vq-input-el'
              value={startText}
              type='text'
              maxlength={8}
              placeholder='开始 00:00'
              placeholderClass='vq-placeholder'
              onInput={(e) => {
                setStartText(e.detail.value)
                setFormError(null)
              }}
            />
          </View>
          <Text className='vq-range-to'>到</Text>
          <View className={`vq-input vq-range-in ${range.error ? 'is-error' : ''}`}>
            <Input
              className='vq-input-el'
              value={endText}
              type='text'
              maxlength={8}
              placeholder='结束 08:45'
              placeholderClass='vq-placeholder'
              onInput={(e) => {
                setEndText(e.detail.value)
                setFormError(null)
              }}
            />
          </View>
        </View>
        <Text className='vq-small vq-range-tip'>不填就按整段视频出题。写成 02:10 这样，也可以只写分钟数。</Text>
      </View>

      <View className='field'>
        <Text className='field-t'>想重点学什么（选填）</Text>
        <View className='vq-focus'>
          <Textarea
            className='vq-focus-el'
            value={focus}
            maxlength={VIDEO_FOCUS_MAX}
            placeholder='比如“复利怎么算”。不填就由 AI 挑这段视频最值得学的内容'
            placeholderClass='vq-placeholder'
            disableDefaultPadding
            onInput={(e) => {
              setFocus(e.detail.value)
              setFormError(null)
            }}
          />
          <Text className='vq-count'>
            {Array.from(focus).length} / {VIDEO_FOCUS_MAX}
          </Text>
        </View>
      </View>

      <View className='field'>
        <Text className='field-t'>题量</Text>
        <View className='vq-len'>
          {COUNTS.map((c) => (
            <View key={c} className={`vq-len-btn ${count === c ? 'is-on' : ''}`} onClick={() => setCount(c)}>
              <Text className='vq-len-n'>{c} 题</Text>
              <Text>约 {estimateMinutes(c)} 分钟</Text>
            </View>
          ))}
        </View>
      </View>

      {(formError || range.error) && (
        <View className='vq-err'>
          <Icon name='warn' />
          <Text>{formError || range.error}</Text>
        </View>
      )}
      <Text className='vq-tip'>AI 会先判断这段视频讲了什么、考哪些知识点，再只依据讲话内容出题；讲解里会标出对应的时间点。</Text>
    </>
  )

  const hint =
    phase.kind === 'pick'
      ? mode === 'file'
        ? '先选一个视频'
        : '先贴一个 B 站链接'
      : busy
        ? '视频还在解析，完成后就能出题'
        : '这个视频暂时出不了题'

  return (
    <View className='screen video-quiz'>
      <NavBar variant='title' title='用视频出题' left='back' />
      <ScrollView scrollY className='scroll'>
        <View className='scroll-inner'>
          {phase.kind === 'pick' && renderSource()}
          {busy && renderProgress()}
          {phase.kind === 'failed' && renderFailed(phase)}
          {phase.kind === 'ready' && renderReady(phase.job)}
          {(phase.kind === 'ready' || phase.kind === 'failed') && (
            <Text className='vq-switch' onClick={() => reset()}>
              换一个视频
            </Text>
          )}
          <View className='vq-pad' />
        </View>
      </ScrollView>
      <View className='foot'>
        {phase.kind === 'pick' && mode === 'link' ? (
          <Btn disabled={!link.trim()} onClick={() => submitLink(linkRef.current)}>
            读取视频
          </Btn>
        ) : (
          <Btn disabled={!job} onClick={onStart}>
            解析并出题
          </Btn>
        )}
        {!job && !(phase.kind === 'pick' && mode === 'link') && <Text className='fine'>{hint}</Text>}
        <SafeBottom />
      </View>
    </View>
  )
}
