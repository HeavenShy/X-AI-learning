/**
 * 用网页出题：原型 02 第 3 屏。
 * 贴链接（进页面时读剪贴板，有链接就自动填好）→ 读取网页给出预览（站点、标题、字数），让用户确认是这篇 →
 * 选填重点、选题量 → 解析并出题。AI 判断主题与出题范围在出题中页进行，不需要用户确认。
 * 预览失败或出题中页带回的错误（打不开 / 读不出正文 / 没有可学内容 / 不合规）在预览卡片里说明原因，给出替代方式。
 */

import { Input, ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow, useRouter, useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import NavBar from '../../components/NavBar'
import { Btn, Icon, SafeBottom } from '../../components/ui'
import { estimateMinutes } from '../../core/format'
import { FIX_COPY, MSG_NOT_URL, previewLine, urlTarget, WEB_FOCUS_MAX, webErrorCopy, type WebFix } from '../../core/web'
import { previewWebPage } from '../../services/api'
import { ApiError, type Pending } from '../../services/request'
import { useStore } from '../../store'
import { ErrorCode, type QuestionCount, type WebPreview } from '../../types/api'
import './index.scss'

const COUNTS: QuestionCount[] = [3, 5, 10]
/** 输入停下多久后自动读取（毫秒） */
const DEBOUNCE_MS = 600

type PreviewState =
  | { phase: 'idle' }
  | { phase: 'not_url' }
  | { phase: 'loading'; target: string }
  | { phase: 'ok'; target: string; data: WebPreview }
  | { phase: 'error'; target: string; code: number | null; message: string }

function decodeParam(v: string | undefined): string {
  if (!v) return ''
  try {
    return decodeURIComponent(v)
  } catch {
    return v
  }
}

export default function WebQuizPage() {
  const initial = decodeParam(useRouter().params.url)
  const [url, setUrl] = useState(initial)
  const [focused, setFocused] = useState(false)
  const [clipTip, setClipTip] = useState(false)
  const [preview, setPreview] = useState<PreviewState>({ phase: 'idle' })
  const [focus, setFocus] = useState('')
  const [count, setCount] = useState<QuestionCount>(5)

  const urlRef = useRef(initial)
  const lastTarget = useRef('')
  const pending = useRef<Pending<WebPreview> | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }

  /** 读取预览；同一个地址不重复读，force 时重读（“再读一次”） */
  const load = (raw: string, force = false) => {
    clearTimer()
    const target = urlTarget(raw)
    if (!target) {
      pending.current?.abort()
      pending.current = null
      lastTarget.current = ''
      setPreview(raw.trim() ? { phase: 'not_url' } : { phase: 'idle' })
      return
    }
    if (!force && target === lastTarget.current) return
    lastTarget.current = target
    pending.current?.abort()
    setPreview({ phase: 'loading', target })
    const p = previewWebPage(target)
    pending.current = p
    p.promise
      .then((data) => {
        if (pending.current === p) setPreview({ phase: 'ok', target, data })
      })
      .catch((e: ApiError) => {
        if (e.code === ErrorCode.ABORTED || pending.current !== p) return
        setPreview({ phase: 'error', target, code: e.code, message: e.message })
      })
  }

  const setUrlValue = (v: string) => {
    urlRef.current = v
    setUrl(v)
  }

  // 进页面：带了链接就直接读；否则看剪贴板里有没有链接（读剪贴板失败 / 未授权都忽略）
  useEffect(() => {
    if (initial) {
      load(initial)
      return
    }
    Taro.getClipboardData()
      .then((res) => {
        const found = urlTarget(res.data || '')
        if (found && /^https?:\/\//i.test(found) && !urlRef.current) {
          setUrlValue(found)
          setClipTip(true)
          load(found)
        }
      })
      .catch(() => undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 从出题中页带回来的错误：显示在预览卡片里，并让下次输入同一地址时重新读取
  useDidShow(() => {
    const { webError, setWebError } = useStore.getState()
    if (!webError) return
    setWebError(null)
    const target = urlTarget(urlRef.current) ?? urlRef.current
    lastTarget.current = ''
    setPreview({ phase: 'error', target, code: webError.code, message: webError.message })
  })

  useUnload(() => {
    clearTimer()
    pending.current?.abort()
  })

  const onInput = (v: string) => {
    setUrlValue(v)
    setClipTip(false)
    clearTimer()
    timer.current = setTimeout(() => load(v), DEBOUNCE_MS)
  }

  const onClear = () => {
    setUrlValue('')
    setClipTip(false)
    load('')
  }

  const onFix = (fix: WebFix) => {
    if (fix === 'retry') load(urlRef.current, true)
    else if (fix === 'paste') Taro.switchTab({ url: '/pages/index/index' })
    else Taro.navigateTo({ url: '/pages/kb-list/index' })
  }

  const ready = preview.phase === 'ok' ? preview.data : null
  const canStart = ready !== null

  const onStart = () => {
    if (!ready) return
    useStore.getState().requestGenerate({
      text: focus.trim(),
      count,
      difficulty: 'mixed',
      web: { url: ready.url, title: ready.title, site: ready.site }
    })
    Taro.navigateTo({ url: '/pages/generating/index' })
  }

  const hint =
    preview.phase === 'loading' ? '正在读取网页…' : preview.phase === 'error' ? '这个链接暂时出不了题' : '先贴一个网页链接'

  const renderPreview = () => {
    switch (preview.phase) {
      case 'idle':
        return <Text className='wq-tip'>支持公众号文章、博客、百科等公开网页；要登录才能看的网页读不了。</Text>
      case 'not_url':
        return (
          <View className='wq-err'>
            <Icon name='warn' />
            <Text>{MSG_NOT_URL}</Text>
          </View>
        )
      case 'loading':
        return (
          <View className='wq-card'>
            <View className='wq-card-h'>
              <Text className='wq-card-t'>网页预览</Text>
              <Text className='pill run'>读取中</Text>
            </View>
            <Text className='wq-small'>正在读取网页，一般几秒钟。</Text>
          </View>
        )
      case 'ok':
        return (
          <View className='wq-card'>
            <View className='wq-card-h'>
              <Text className='wq-card-t'>网页预览</Text>
              <Text className='pill ok'>已读取</Text>
            </View>
            <View className='wq-preview'>
              <View className='wq-thumb'>
                <Icon name='docInk' />
              </View>
              <View className='wq-meta'>
                <Text className='wq-site'>{preview.data.site}</Text>
                <Text className='wq-title'>{preview.data.title}</Text>
                <Text className='wq-small'>{previewLine(preview.data)}</Text>
              </View>
            </View>
          </View>
        )
      case 'error': {
        const copy = webErrorCopy(preview.code, preview.message)
        return (
          <View className='wq-card is-error'>
            <Text className='wq-fail-h'>{copy.title}</Text>
            <Text className='wq-fail-p'>{copy.text}</Text>
            {copy.fixes.length > 0 && (
              <View className='wq-fixes'>
                {copy.fixes.map((f) => (
                  <View key={f} className='wq-fix' hoverClass='wq-fix-pressed' onClick={() => onFix(f)}>
                    <View className='wq-fix-t'>
                      <Text className='wq-fix-title'>{FIX_COPY[f].title}</Text>
                      <Text className='wq-small'>{FIX_COPY[f].sub}</Text>
                    </View>
                    <Text className='wq-chev'>›</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )
      }
    }
  }

  return (
    <View className='screen web-quiz'>
      <NavBar variant='title' title='用网页出题' left='back' />
      <ScrollView scrollY className='scroll'>
        <View className='scroll-inner'>
          <View className='field first'>
            <Text className='field-t'>网页链接</Text>
            <View
              className={`wq-input ${focused ? 'is-focus' : ''} ${preview.phase === 'error' || preview.phase === 'not_url' ? 'is-error' : ''}`}
            >
              <Icon name='linkInk' className='wq-input-i' />
              <Input
                className='wq-input-el'
                value={url}
                type='text'
                confirmType='go'
                maxlength={2000}
                placeholder='粘贴网页链接，比如公众号文章'
                placeholderClass='wq-placeholder'
                onInput={(e) => onInput(e.detail.value)}
                onFocus={() => setFocused(true)}
                onBlur={() => {
                  setFocused(false)
                  load(urlRef.current)
                }}
                onConfirm={() => load(urlRef.current)}
              />
              {url && (
                <View className='wq-clear' onClick={onClear}>
                  <Icon name='close' />
                </View>
              )}
            </View>
            {clipTip && (
              <View className='wq-clip'>
                <Icon name='ok' />
                <Text>检测到剪贴板里有链接，已帮你填好。</Text>
              </View>
            )}
          </View>

          {renderPreview()}

          <View className='field'>
            <Text className='field-t'>想重点学什么（选填）</Text>
            <View className='wq-focus'>
              <Textarea
                className='wq-focus-el'
                value={focus}
                maxlength={WEB_FOCUS_MAX}
                placeholder='比如“和微调怎么选”。不填就由 AI 挑这篇最值得学的内容'
                placeholderClass='wq-placeholder'
                disableDefaultPadding
                onInput={(e) => setFocus(e.detail.value)}
              />
              <Text className='wq-count'>
                {Array.from(focus).length} / {WEB_FOCUS_MAX}
              </Text>
            </View>
          </View>

          <View className='field'>
            <Text className='field-t'>题量</Text>
            <View className='wq-len'>
              {COUNTS.map((c) => (
                <View key={c} className={`wq-len-btn ${count === c ? 'is-on' : ''}`} onClick={() => setCount(c)}>
                  <Text className='wq-len-n'>{c} 题</Text>
                  <Text>约 {estimateMinutes(c)} 分钟</Text>
                </View>
              ))}
            </View>
          </View>

          <Text className='wq-tip'>AI 会先判断这篇讲什么、考哪些知识点，再只依据网页内容出题；每道题都附原文摘录。</Text>
          <View className='wq-pad' />
        </View>
      </ScrollView>
      <View className='foot'>
        <Btn disabled={!canStart} onClick={onStart}>
          解析并出题
        </Btn>
        {!canStart && <Text className='fine'>{hint}</Text>}
        <SafeBottom />
      </View>
    </View>
  )
}
