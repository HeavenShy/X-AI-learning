/**
 * 我的知识库：原型 02 第 7 屏（列表）。
 * 顶部资料用量，列表是各知识库（资料数、更新时间），底部新建。长按知识库：改名 / 删除（删除前确认）。
 * 从“我的”页“我的知识库”和首页“传文档”进入。
 */

import { ScrollView, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'

import Empty from '../../components/Empty'
import KbNameDialog from '../../components/KbNameDialog'
import NavBar from '../../components/NavBar'
import { Btn, Dialog, Icon, SafeBottom } from '../../components/ui'
import { kbSubline, loadErrorCopy, quotaPercent } from '../../core/kb'
import { createKnowledgeBase, deleteKnowledgeBase, listKnowledgeBases, renameKnowledgeBase } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import { ApiError } from '../../services/request'
import type { KbList, KnowledgeBase } from '../../types/api'
import './index.scss'

type Editing = { kind: 'create' } | { kind: 'rename'; kb: KnowledgeBase } | null

export default function KbListPage() {
  const [data, setData] = useState<KbList | null>(null)
  const [errorCode, setErrorCode] = useState<number | null | undefined>(undefined)
  const [editing, setEditing] = useState<Editing>(null)
  const [deleting, setDeleting] = useState<KnowledgeBase | null>(null)

  const load = async () => {
    try {
      if (!(await ensureLogin())) throw new ApiError(-1, '未登录')
      setData(await listKnowledgeBases().promise)
      setErrorCode(undefined)
    } catch (e) {
      console.warn('[kb-list] 加载失败', e)
      setErrorCode(e instanceof ApiError ? e.code : null)
    }
  }

  // 从详情页回来时资料数、名称可能变了
  useDidShow(() => {
    void load()
  })

  const openDetail = (kb: KnowledgeBase) =>
    Taro.navigateTo({ url: `/pages/kb-detail/index?kb_id=${encodeURIComponent(kb.kb_id)}` })

  const onLongPress = (kb: KnowledgeBase) => {
    Taro.showActionSheet({ itemList: ['改名', '删除'] })
      .then(({ tapIndex }) => {
        if (tapIndex === 0) setEditing({ kind: 'rename', kb })
        else if (tapIndex === 1) setDeleting(kb)
      })
      .catch(() => {
        // 用户取消
      })
  }

  const onCreate = async (name: string) => {
    const kb = await createKnowledgeBase(name).promise
    setEditing(null)
    // 建好直接进详情上传资料（原型：“创建，然后上传资料”）
    Taro.navigateTo({ url: `/pages/kb-detail/index?kb_id=${encodeURIComponent(kb.kb_id)}` })
  }

  const onRename = async (kb: KnowledgeBase, name: string) => {
    await renameKnowledgeBase(kb.kb_id, name).promise
    setEditing(null)
    void load()
  }

  const onDelete = async (kb: KnowledgeBase) => {
    setDeleting(null)
    Taro.showLoading({ title: '删除中', mask: true })
    try {
      await deleteKnowledgeBase(kb.kb_id).promise
      Taro.hideLoading()
      Taro.showToast({ title: '已删除', icon: 'success' })
      void load()
    } catch (e) {
      Taro.hideLoading()
      Taro.showToast({ title: e instanceof ApiError ? e.message : '没删掉，稍后再试', icon: 'none' })
    }
  }

  const shell = (body: JSX.Element, foot = true) => (
    <View className='screen kb-list'>
      <NavBar variant='title' title='我的知识库' left='back' />
      {body}
      {foot ? (
        <View className='foot'>
          <Btn kind='ghost' onClick={() => setEditing({ kind: 'create' })}>
            ＋ 新建知识库
          </Btn>
          <SafeBottom />
        </View>
      ) : (
        <SafeBottom />
      )}
      {editing?.kind === 'create' && (
        <KbNameDialog title='新建知识库' confirm='创建' onSubmit={onCreate} onClose={() => setEditing(null)} />
      )}
      {editing?.kind === 'rename' && (
        <KbNameDialog
          title='改名'
          initial={editing.kb.name}
          confirm='保存'
          onSubmit={(name) => onRename(editing.kb, name)}
          onClose={() => setEditing(null)}
        />
      )}
      {deleting && (
        <Dialog
          title='删除这个知识库？'
          text={`“${deleting.name}”里的 ${deleting.document_count} 份资料会一起删除，不能恢复。已经出过的题和错题会保留。`}
          primary='删除'
          ghost='取消'
          onPrimary={() => void onDelete(deleting)}
          onGhost={() => setDeleting(null)}
        />
      )}
    </View>
  )

  // 首次加载中：只留导航栏
  if (!data && errorCode === undefined) return shell(<View className='content' />, false)

  if (!data) {
    const copy = loadErrorCopy(errorCode ?? null)
    return shell(
      <View className='content'>
        <Empty frame='知识库' title={copy.title} text={copy.text} action='重试' onAction={() => void load()} />
      </View>,
      false
    )
  }

  const now = Date.now()
  // 空状态自带“新建知识库”按钮，底栏就不再重复
  const empty = data.items.length === 0
  return shell(
    <ScrollView scrollY className='scroll'>
      <View className='scroll-inner'>
        <Text className='page-sub'>用自己的资料出题，题目只来自库里的内容。</Text>
        <View className='quota'>
          <View className='q-row'>
            <Text>已存资料</Text>
            <Text>
              {data.document_total} / {data.document_limit} 份
            </Text>
          </View>
          <View className='q-track'>
            <View className='q-fill' style={{ width: `${quotaPercent(data.document_total, data.document_limit)}%` }} />
          </View>
        </View>

        {empty ? (
          <View className='kb-empty'>
            <Empty
              frame='空书架'
              title='还没有知识库'
              text='建一个库，把教材、制度、手册传进去，就能按资料出题。'
              action='新建知识库'
              onAction={() => setEditing({ kind: 'create' })}
            />
          </View>
        ) : (
          <>
            <View className='list kb-items'>
              {data.items.map((kb) => (
                <View
                  key={kb.kb_id}
                  className='li'
                  hoverClass='li-pressed'
                  onClick={() => openDetail(kb)}
                  onLongPress={() => onLongPress(kb)}
                >
                  <View className='ico y'>
                    <Icon name='folder' />
                  </View>
                  <View className='grow'>
                    <Text className='kb-name'>{kb.name}</Text>
                    <Text className='small'>{kbSubline(kb, now)}</Text>
                  </View>
                  <View className='chev' />
                </View>
              ))}
            </View>
            <Text className='kb-tip'>长按知识库可以改名或删除</Text>
          </>
        )}
        <Text className='kb-tip'>资料的文字会交给第三方服务（硅基流动）做向量化，只用于给你出题。</Text>
        <View className='kb-pad' />
      </View>
    </ScrollView>,
    !empty
  )
}
