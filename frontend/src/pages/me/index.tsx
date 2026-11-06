/**
 * 我的：原型 03 第 1 屏（pages/me）。
 * 顶部身份和等级，三个数字回答“我学了多少”；列表里开放“历史记录”“我的知识库”，其余入口置灰。
 * 点头像或昵称可以改昵称（微信“头像昵称填写能力”：type=nickname 的输入框）。
 */

import { Button, Form, Input, Text, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useEffect, useState } from 'react'

import NavBar from '../../components/NavBar'
import { setTabBarHidden, TabBarSpace, useTabSelected } from '../../components/TabPage'
import { Icon, StatChip } from '../../components/ui'
import type { IconName } from '../../assets/icons'
import { levelSpan } from '../../core/level'
import { avatarChar, cleanNickname, NICKNAME_MAX, validateNickname } from '../../core/nickname'
import { TAB_INDEX } from '../../core/tabs'
import { refreshProfile } from '../../services/account'
import { updateProfile } from '../../services/api'
import { ensureLogin } from '../../services/auth'
import { ApiError } from '../../services/request'
import { useStore } from '../../store'
import './index.scss'

const DEFAULT_NICKNAME = '学习者'
const MSG_NICKNAME_REVIEW = '这个昵称不太合适，换一个试试'

interface Entry {
  icon: IconName
  text: string
  url?: string
  yellow?: boolean
}

/** 原型列表的六个入口；没有 url 的本期未开放 */
const ENTRIES: Entry[] = [
  { icon: 'chartGrey', text: '学习数据' },
  { icon: 'treeGrey', text: '知识树' },
  { icon: 'clock', text: '历史记录', url: '/pages/history/index' },
  { icon: 'crossBookGrey', text: '错题本' },
  { icon: 'folder', text: '我的知识库', url: '/pages/kb-list/index' },
  { icon: 'crownGrey', text: '会员', yellow: true }
]

function NicknameDialog({ initial, onClose }: { initial: string; onClose: () => void }) {
  const [value, setValue] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // 微信会在失焦时异步审核昵称，不通过会清空输入；按文档用表单提交读取最终值
  const onSubmit = async (e: { detail: { value?: Record<string, any> } }) => {
    if (saving) return
    const raw = String(e.detail.value?.nickname ?? value)
    const err = validateNickname(raw)
    if (err) {
      setError(err)
      return
    }
    const nickname = cleanNickname(raw)
    if (nickname === initial) {
      onClose()
      return
    }
    setSaving(true)
    try {
      if (!(await ensureLogin())) throw new ApiError(-1, '没连上服务，稍后再试')
      const p = await updateProfile({ nickname }).promise
      useStore.getState().applyProfile(p)
      onClose()
    } catch (err2) {
      setError(err2 instanceof ApiError ? err2.message : '没保存上，稍后再试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <View className='scrim' catchMove>
      <Form className='dialog nick-dialog' onSubmit={onSubmit}>
        <Text className='d-title'>改个昵称</Text>
        <Text className='d-text'>点输入框，键盘上方可以直接填微信昵称。</Text>
        <View className={`input ${error ? 'is-error' : ''}`}>
          <Input
            className='input-el'
            type='nickname'
            name='nickname'
            value={value}
            maxlength={NICKNAME_MAX}
            placeholder='写一个昵称'
            focus
            onInput={(e) => {
              setValue(e.detail.value)
              if (error) setError(null)
            }}
            onNickNameReview={(e) => {
              if (!e.detail.pass) setError(MSG_NICKNAME_REVIEW)
            }}
          />
        </View>
        {error && (
          <View className='nick-err'>
            <Icon name='warn' />
            <Text>{error}</Text>
          </View>
        )}
        <View className='row'>
          <Button className={`btn btn-primary form-btn ${saving ? 'is-disabled' : ''}`} formType='submit' hoverClass='btn-pressed'>
            {saving ? '保存中' : '保存'}
          </Button>
          <View className='btn btn-ghost' hoverClass='btn-pressed' onClick={onClose}>
            取消
          </View>
        </View>
      </Form>
    </View>
  )
}

export default function Me() {
  const profile = useStore((s) => s.profile)
  const me = useStore((s) => s.me)
  const [editing, setEditing] = useState(false)

  useTabSelected(TAB_INDEX.me)
  useDidShow(() => {
    void refreshProfile()
  })

  // 自定义 tabBar 在页面之上，遮罩盖不住它：弹窗打开时先收起标签栏
  useEffect(() => {
    if (!editing) return
    setTabBarHidden(true)
    return () => setTabBarHidden(false)
  }, [editing])

  const nickname = me?.nickname || DEFAULT_NICKNAME
  const lv = levelSpan(profile.xp)
  const stats = me
    ? [
        { n: String(me.quiz_count), label: '已学话数' },
        { n: String(me.week_minutes), label: '本周分钟' },
        { n: `${me.average_accuracy}%`, label: '总正确率' }
      ]
    : [
        { n: String(profile.episodes), label: '已学话数' },
        { n: '--', label: '本周分钟' },
        { n: '--', label: '总正确率' }
      ]

  const onEntry = (e: Entry) => {
    if (e.url) Taro.navigateTo({ url: e.url })
    else Taro.showToast({ title: '即将上线', icon: 'none' })
  }

  return (
    <View className='screen me-screen'>
      <NavBar />
      <View className='content me-page'>
        <View className='me'>
          <View className='avatar' onClick={() => setEditing(true)}>
            <Text>{avatarChar(nickname)}</Text>
          </View>
          <View className='grow'>
            <View className='me-b'>
              <Text className='me-name' onClick={() => setEditing(true)}>
                {nickname}
              </Text>
              <StatChip icon='coin' className='me-coin'>
                {profile.coins}
              </StatChip>
            </View>
            <View className='xpline'>
              <Text className='lvchip me-lv'>{lv.label}</Text>
              <View className='track'>
                <View className='track-i' style={{ width: `${lv.percent}%` }} />
              </View>
              <Text>{lv.total ? `${lv.current} / ${lv.total}` : `${lv.current}`}</Text>
            </View>
          </View>
        </View>

        <View className='stat3'>
          {stats.map((s) => (
            <View key={s.label} className='stat'>
              <Text className='stat-b'>{s.n}</Text>
              <Text>{s.label}</Text>
            </View>
          ))}
        </View>

        <View className='list me-list'>
          {ENTRIES.map((e) => (
            <View
              key={e.text}
              className={`li ${e.url ? '' : 'is-off'}`}
              hoverClass={e.url ? 'li-pressed' : 'none'}
              onClick={() => onEntry(e)}
            >
              <View className={`ico ${e.yellow ? 'y' : ''}`}>
                <Icon name={e.icon} />
              </View>
              <Text className='grow'>{e.text}</Text>
              <View className='chev' />
            </View>
          ))}
        </View>
      </View>
      <TabBarSpace />
      {editing && <NicknameDialog initial={me?.nickname ?? ''} onClose={() => setEditing(false)} />}
    </View>
  )
}
