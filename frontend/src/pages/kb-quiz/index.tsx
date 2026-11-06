/**
 * 用知识库出题：原型 02 第 10 屏（本期只做“练习”模式，不做模拟考试）。
 * 勾选资料（默认全选可出题的，未就绪的不能勾并显示状态）、选填重点、选题量，然后进入出题中页。
 * 出题中页遇到资料未就绪（4023）或重点不合规（4003）会回到这里，在页面上提示原因。
 */

import { ScrollView, Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { useState } from 'react'

import Empty from '../../components/Empty'
import NavBar, { goBackOrHome } from '../../components/NavBar'
import { Btn, Icon, SafeBottom } from '../../components/ui'
import { estimateMinutes } from '../../core/format'
import {
  defaultSelection,
  KB_FOCUS_MAX,
  loadErrorCopy,
  readyDocuments,
  selectedIds,
  STATUS_LABEL,
  toggleSelection
} from '../../core/kb'
import { getKnowledgeBase } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import { ApiError } from '../../services/request'
import { useStore } from '../../store'
import type { KbDetail, QuestionCount } from '../../types/api'
import './index.scss'

const COUNTS: QuestionCount[] = [3, 5, 10]

export default function KbQuizPage() {
  const kbId = useRouter().params.kb_id ?? ''
  const [detail, setDetail] = useState<KbDetail | null>(null)
  const [errorCode, setErrorCode] = useState<number | null | undefined>(undefined)
  const [selected, setSelected] = useState<string[] | null>(null)
  const [focus, setFocus] = useState('')
  const [count, setCount] = useState<QuestionCount>(5)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    try {
      if (!(await ensureLogin())) throw new ApiError(-1, '未登录')
      const d = await getKnowledgeBase(kbId).promise
      setDetail(d)
      setErrorCode(undefined)
      // 第一次进来默认勾选全部可出题资料；之后保留用户的选择（去掉已不可用的）
      setSelected((prev) => {
        const ready = defaultSelection(d.documents)
        return prev === null ? ready : prev.filter((id) => ready.includes(id))
      })
    } catch (e) {
      console.warn('[kb-quiz] 加载失败', e)
      setErrorCode(e instanceof ApiError ? e.code : null)
    }
  }

  useDidShow(() => {
    // 从出题中页带回来的错误
    const { kbError, setKbError } = useStore.getState()
    if (kbError) {
      setError(kbError)
      setKbError(null)
    }
    void load()
  })

  const shell = (body: JSX.Element) => (
    <View className='screen kb-quiz'>
      <NavBar variant='title' title='用知识库出题' left='back' />
      {body}
    </View>
  )

  if (!detail && errorCode === undefined) return shell(<View className='content' />)

  if (!detail) {
    const copy = loadErrorCopy(errorCode ?? null)
    const notFound = errorCode === 4040
    return shell(
      <>
        <View className='content'>
          <Empty
            frame='知识库'
            title={copy.title}
            text={copy.text}
            action={notFound ? '返回' : '重试'}
            onAction={() => (notFound ? goBackOrHome() : void load())}
          />
        </View>
        <SafeBottom />
      </>
    )
  }

  const docs = detail.documents
  const picked = selected ?? []
  const readyCount = readyDocuments(docs).length
  const canStart = picked.length > 0

  const onStart = () => {
    if (!canStart) return
    useStore.getState().requestGenerate({
      text: focus.trim(),
      count,
      difficulty: 'mixed',
      kb: { kbId: detail.knowledge_base.kb_id, kbName: detail.knowledge_base.name, documentIds: selectedIds(docs, picked) }
    })
    Taro.navigateTo({ url: '/pages/generating/index' })
  }

  return shell(
    <>
      <ScrollView scrollY className='scroll'>
        <View className='scroll-inner'>
          <View className='sec-t first'>
            <Text>从哪些资料出</Text>
            <Text className='sec-s'>已选 {picked.length} 份</Text>
          </View>
          {docs.length === 0 ? (
            <View className='kq-none'>
              <Text>这个知识库还没有资料，先回去上传一份吧。</Text>
            </View>
          ) : (
            <View className='list'>
              {docs.map((d) => {
                const ready = d.status === 'ready'
                const on = picked.includes(d.document_id)
                return (
                  <View
                    key={d.document_id}
                    className={`li ${ready ? '' : 'is-off'}`}
                    hoverClass={ready ? 'li-pressed' : 'none'}
                    onClick={() => {
                      if (!ready) return
                      setSelected(toggleSelection(picked, d))
                      if (error) setError(null)
                    }}
                  >
                    <View className={`check ${on ? 'on' : ''} ${ready ? '' : 'is-off'}`} />
                    <View className='grow'>
                      <Text className='doc-name'>{d.filename}</Text>
                      {!ready && (
                        <Text className='small'>
                          {d.status === 'processing' ? '处理中，完成后可选' : `${STATUS_LABEL[d.status]}：${d.fail_reason ?? ''}`}
                        </Text>
                      )}
                    </View>
                  </View>
                )
              })}
            </View>
          )}
          {readyCount === 0 && docs.length > 0 && (
            <Text className='kq-tip'>还没有可出题的资料：先上传资料，或等处理完成再来。</Text>
          )}

          <View className='field'>
            <Text className='field-t'>想重点学什么（选填）</Text>
            <View className={`kq-focus ${error ? 'is-error' : ''}`}>
              <Textarea
                className='kq-focus-el'
                value={focus}
                maxlength={KB_FOCUS_MAX}
                placeholder='比如“报销审批流程”。不填就从所选资料里均匀出题'
                placeholderClass='kq-placeholder'
                disableDefaultPadding
                onInput={(e) => {
                  setFocus(e.detail.value)
                  if (error) setError(null)
                }}
              />
              <Text className='kq-count'>
                {Array.from(focus).length} / {KB_FOCUS_MAX}
              </Text>
            </View>
          </View>

          <View className='field'>
            <Text className='field-t'>题量</Text>
            <View className='kq-len'>
              {COUNTS.map((c) => (
                <View key={c} className={`kq-len-btn ${count === c ? 'is-on' : ''}`} onClick={() => setCount(c)}>
                  <Text className='kq-len-n'>{c} 题</Text>
                  <Text>约 {estimateMinutes(c)} 分钟</Text>
                </View>
              ))}
            </View>
          </View>

          {error && (
            <View className='kq-err'>
              <Icon name='warn' />
              <Text>{error}</Text>
            </View>
          )}
          <Text className='kq-tip'>题目和讲解只依据所选资料，不联网；每道题都会标出处。</Text>
          <View className='kq-pad' />
        </View>
      </ScrollView>
      <View className='foot'>
        <Btn disabled={!canStart} onClick={onStart}>
          开始出题
        </Btn>
        {!canStart && <Text className='fine'>先上传资料，或等处理完成</Text>}
        <SafeBottom />
      </View>
    </>
  )
}
