/**
 * 知识库详情：原型 02 第 9 屏。
 * - 资料列表与状态（处理中 / 可出题 / 失败 + 原因），按上传时间新到旧。
 * - “上传”从微信聊天里选文件（chooseMessageFile），本地预检后 uploadFile；后端立即返回“处理中”。
 * - 有资料处理中时每 3 秒刷新一次详情，处理完或离开页面（隐藏 / 卸载）就停。
 * - 长按资料删除（先确认）；“用这个库出题”进入出题设置页。
 * H5 没有 chooseMessageFile，只提示去微信里上传。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro, { useDidHide, useDidShow, useRouter, useUnload } from '@tarojs/taro'
import { useEffect, useRef, useState } from 'react'

import Empty from '../../components/Empty'
import NavBar, { goBackOrHome } from '../../components/NavBar'
import { Btn, Dialog, Icon, SafeBottom } from '../../components/ui'
import {
  documentSubline,
  hasProcessing,
  KB_EXTENSIONS,
  KB_POLL_MS,
  loadErrorCopy,
  precheckFile,
  STATUS_LABEL,
  STATUS_PILL
} from '../../core/kb'
import { deleteDocument, getKnowledgeBase, uploadDocument } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import { ApiError } from '../../services/request'
import type { KbDetail, KbDocument } from '../../types/api'
import './index.scss'

const MSG_H5 = '请在微信小程序里上传：从聊天里选文件'

function alertUpload(content: string) {
  Taro.showModal({ title: '没传上去', content, showCancel: false, confirmText: '知道了' })
}

export default function KbDetailPage() {
  const kbId = useRouter().params.kb_id ?? ''
  const [detail, setDetail] = useState<KbDetail | null>(null)
  const [errorCode, setErrorCode] = useState<number | null | undefined>(undefined)
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState<KbDocument | null>(null)
  // 轮询失败时 detail 不变，用它触发下一轮
  const [pollTick, setPollTick] = useState(0)
  const visible = useRef(true)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stopPolling = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }

  const load = async (quiet = false) => {
    try {
      if (!(await ensureLogin())) throw new ApiError(-1, '未登录')
      const d = await getKnowledgeBase(kbId).promise
      setDetail(d)
      setErrorCode(undefined)
    } catch (e) {
      console.warn('[kb-detail] 加载失败', e)
      // 轮询时偶尔失败不打断页面，下一轮再试
      if (quiet && detail) setPollTick((n) => n + 1)
      else setErrorCode(e instanceof ApiError ? e.code : null)
    }
  }

  // 有处理中的资料就排下一次刷新；详情更新后重新判断
  useEffect(() => {
    stopPolling()
    if (detail && hasProcessing(detail.documents) && visible.current) {
      timer.current = setTimeout(() => void load(true), KB_POLL_MS)
    }
    return stopPolling
  }, [detail, pollTick])

  useDidShow(() => {
    visible.current = true
    void load()
  })
  useDidHide(() => {
    visible.current = false
    stopPolling()
  })
  useUnload(() => {
    visible.current = false
    stopPolling()
  })

  const onUpload = async () => {
    if (uploading) return
    if (process.env.TARO_ENV !== 'weapp') {
      Taro.showToast({ title: MSG_H5, icon: 'none' })
      return
    }
    let file: { path: string; size: number; name: string }
    try {
      const res = await Taro.chooseMessageFile({ count: 1, type: 'file', extension: [...KB_EXTENSIONS] })
      file = res.tempFiles[0]
      if (!file) return
    } catch {
      return // 用户取消选择
    }
    const err = precheckFile(file)
    if (err) {
      alertUpload(err)
      return
    }
    setUploading(true)
    Taro.showLoading({ title: '上传中', mask: true })
    try {
      const doc = await uploadDocument(kbId, file.path).promise
      Taro.hideLoading()
      setDetail((d) => (d ? { ...d, documents: [doc, ...d.documents.filter((x) => x.document_id !== doc.document_id)] } : d))
    } catch (e) {
      Taro.hideLoading()
      alertUpload(e instanceof ApiError ? e.message : '网络好像断了，稍后再试')
    } finally {
      setUploading(false)
    }
  }

  const onDelete = async (doc: KbDocument) => {
    setDeleting(null)
    try {
      await deleteDocument(kbId, doc.document_id).promise
      setDetail((d) => (d ? { ...d, documents: d.documents.filter((x) => x.document_id !== doc.document_id) } : d))
      Taro.showToast({ title: '已删除', icon: 'success' })
      void load(true)
    } catch (e) {
      Taro.showToast({ title: e instanceof ApiError ? e.message : '没删掉，稍后再试', icon: 'none' })
    }
  }

  const shell = (title: string, body: JSX.Element) => (
    <View className='screen kb-detail'>
      <NavBar variant='title' title={title} left='back' />
      {body}
      <SafeBottom />
      {deleting && (
        <Dialog
          title='删除这份资料？'
          text={`“${deleting.filename}”的文字和向量会一起删除，之后出题不再用到它。已经出过的题会保留出处。`}
          primary='删除'
          ghost='取消'
          onPrimary={() => void onDelete(deleting)}
          onGhost={() => setDeleting(null)}
        />
      )}
    </View>
  )

  if (!detail && errorCode === undefined) return shell('知识库', <View className='content' />)

  if (!detail) {
    const copy = loadErrorCopy(errorCode ?? null)
    const notFound = errorCode === 4040
    return shell(
      '知识库',
      <View className='content'>
        <Empty
          frame='知识库'
          title={copy.title}
          text={copy.text}
          action={notFound ? '返回' : '重试'}
          onAction={() => (notFound ? goBackOrHome() : void load())}
        />
      </View>
    )
  }

  const { knowledge_base: kb, documents } = detail
  const ready = documents.filter((d) => d.status === 'ready').length
  const processing = documents.filter((d) => d.status === 'processing').length

  return shell(
    '知识库',
    <ScrollView scrollY className='scroll'>
      <View className='scroll-inner'>
        <View className='lib-head'>
          <Text className='lib-name'>{kb.name}</Text>
          <Text className='lib-sub'>
            {documents.length ? `${documents.length} 份资料，${ready} 份可出题` : '还没有资料'}
            {processing ? `，${processing} 份处理中` : ''}
          </Text>
          <View className='lib-actions'>
            <Btn kind='ghost' className='lib-up' disabled={uploading} onClick={() => void onUpload()}>
              {uploading ? '上传中' : '上传'}
            </Btn>
            <Btn
              className='lib-go'
              onClick={() => Taro.navigateTo({ url: `/pages/kb-quiz/index?kb_id=${encodeURIComponent(kb.kb_id)}` })}
            >
              用这个库出题
            </Btn>
          </View>
        </View>

        <View className='sec-t'>
          <Text>资料</Text>
          <Text className='sec-s'>按上传时间</Text>
        </View>
        {documents.length === 0 ? (
          <View className='lib-empty'>
            <Text className='lib-empty-t'>点“上传”，从微信聊天里选一份文件</Text>
            <Text className='lib-empty-p'>支持 PDF（文字版）、Word（.docx）、TXT、Markdown，单个 20 MB 以内。</Text>
          </View>
        ) : (
          <View className='list'>
            {documents.map((d) => (
              <View
                key={d.document_id}
                className='li'
                hoverClass='li-pressed'
                onLongPress={() => setDeleting(d)}
              >
                <View className='ico'>
                  <Icon name='docInk' />
                </View>
                <View className='grow'>
                  <Text className='doc-name'>{d.filename}</Text>
                  <Text className={`small ${d.status === 'failed' ? 'is-fail' : ''}`}>{documentSubline(d)}</Text>
                </View>
                <Text className={`pill ${STATUS_PILL[d.status]}`}>{STATUS_LABEL[d.status]}</Text>
              </View>
            ))}
          </View>
        )}
        <Text className='kb-tip'>
          {documents.length ? '长按资料可以删除。' : ''}资料的文字会交给第三方服务（硅基流动）做向量化，只用于给你出题；原文件处理完就删除。
        </Text>
        <View className='kb-pad' />
      </View>
    </ScrollView>
  )
}
