/**
 * 分享海报：原型 01 第 17、18 屏。
 * 页面用 View 还原预览；保存 / 转发时用隐藏的 Canvas 2D 按同一版式绘制并导出图片。
 * 按需求不放任何排名。小程序码先用太阳码占位（真码需要后端用 AppSecret 调 wxacode.getUnlimited）。
 */

import { Canvas, Text, View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { useEffect, useMemo, useRef, useState } from 'react'

import NavBar from '../../components/NavBar'
import { Btn, SafeBottom, Toast } from '../../components/ui'
import { formatDuration } from '../../core/format'
import { sunCodeSvg, svgUri } from '../../core/graphics'
import { sessionStats } from '../../core/session'
import { loadDisplayFont } from '../../services/font'
import { drawPoster, POSTER_H, POSTER_W, type PosterData } from '../../services/poster'
import { useStore } from '../../store'
import './index.scss'

const CANVAS_ID = 'poster-canvas'

async function renderPosterImage(data: PosterData): Promise<string> {
  await loadDisplayFont()
  const res = await new Promise<{ node: any }>((resolve, reject) => {
    Taro.createSelectorQuery()
      .select(`#${CANVAS_ID}`)
      .fields({ node: true, size: true })
      .exec((r) => (r && r[0] && r[0].node ? resolve(r[0]) : reject(new Error('canvas not found'))))
  })
  const canvas = res.node
  const dpr = Math.min(3, Taro.getWindowInfo().pixelRatio || 2)
  canvas.width = POSTER_W * dpr
  canvas.height = POSTER_H * dpr
  const ctx = canvas.getContext('2d') as CanvasRenderingContext2D
  ctx.scale(dpr, dpr)
  drawPoster(ctx, data)
  const out = await Taro.canvasToTempFilePath({ canvas, fileType: 'png' } as Taro.canvasToTempFilePath.Option)
  return out.tempFilePath
}

const isAuthDenied = (errMsg = '') => /auth deny|auth denied|authorize no response|permission/i.test(errMsg)

export default function Poster() {
  const session = useStore((s) => s.session)
  const report = useStore((s) => s.report)
  const [toast, setToast] = useState(false)
  const [busy, setBusy] = useState(false)
  const imagePath = useRef<string | null>(null)
  const sunUri = useMemo(() => svgUri(sunCodeSvg()), [])

  const quote = report?.status === 'done' && report.data ? report.data.share_quote : ''

  // 进入时检查一次：没有完结的会话或报告就回首页
  useEffect(() => {
    const { session: s, report: r } = useStore.getState()
    if (!s || !s.finished || r?.status !== 'done') Taro.reLaunch({ url: '/pages/index/index' })
  }, [])

  if (!session || !session.finished || !quote) return <View className='screen poster-screen' />

  const st = sessionStats(session)
  const data: PosterData = {
    episode: session.reward?.episode ?? 1,
    title: session.quiz.title,
    quote,
    correct: st.correct,
    total: st.total,
    duration: formatDuration(st.durationMs)
  }

  const getImage = async () => {
    if (!imagePath.current) imagePath.current = await renderPosterImage(data)
    return imagePath.current
  }

  const withBusy = async (fn: () => Promise<void>) => {
    if (busy) return
    setBusy(true)
    try {
      await fn()
    } finally {
      setBusy(false)
    }
  }

  const onSave = () =>
    withBusy(async () => {
      try {
        const filePath = await getImage()
        await Taro.saveImageToPhotosAlbum({ filePath })
        setToast(true)
        setTimeout(() => setToast(false), 1600)
      } catch (err: any) {
        const msg = err?.errMsg || ''
        if (/cancel/i.test(msg)) return
        if (isAuthDenied(msg)) {
          const r = await Taro.showModal({
            title: '需要相册权限',
            content: '需要相册权限才能保存，可在设置里打开',
            confirmText: '去设置'
          })
          if (r.confirm) await Taro.openSetting()
          return
        }
        Taro.showToast({ title: '海报生成失败，请重试', icon: 'none' })
      }
    })

  const onShare = () =>
    withBusy(async () => {
      try {
        const path = await getImage()
        await Taro.showShareImageMenu({ path })
      } catch (err: any) {
        if (!/cancel/i.test(err?.errMsg || '')) Taro.showToast({ title: '暂时无法转发，可先保存到相册', icon: 'none' })
      }
    })

  return (
    <View className='screen poster-screen'>
      <NavBar variant='title' title='分享海报' left='back' dark />
      <View className='content poster-content'>
        <View className={`poster ${toast ? 'is-dim' : ''}`}>
          <View className='p-top'>
            <Text>一话一懂</Text>
            <Text className='p-ep'>我的第 {data.episode} 话</Text>
          </View>
          <View className='p-hero'>
            <Text className='p-h3'>我看懂了{'\n'}{data.title}</Text>
            <Text className='balloon p-balloon'>{data.quote}</Text>
          </View>
          <View className='p-stats'>
            <View className='p-stat'>
              <Text className='p-stat-b'>
                {data.correct} / {data.total}
              </Text>
              <Text>答对格数</Text>
            </View>
            <View className='p-stat'>
              <Text className='p-stat-b'>{data.duration}</Text>
              <Text>用时</Text>
            </View>
          </View>
          <View className='p-qr'>
            <View className='p-sun icon' style={{ backgroundImage: `url("${sunUri}")` }}>
              <Text className='p-sun-c'>懂</Text>
            </View>
            <View className='p-qr-t'>
              <Text className='p-qr-b'>扫码，下一话你来</Text>
              <Text>输入任意知识，AI 帮你出题</Text>
            </View>
          </View>
        </View>
      </View>
      <View className='poster-actions'>
        <Btn onClick={onSave}>保存到相册</Btn>
        <Btn kind='ghost' className='pa-ghost' onClick={onShare}>
          转发给好友
        </Btn>
      </View>
      <SafeBottom clear />
      {toast && <Toast text='已保存到相册' />}
      <Canvas type='2d' id={CANVAS_ID} className='poster-canvas' style={{ width: `${POSTER_W}px`, height: `${POSTER_H}px` }} />
    </View>
  )
}
