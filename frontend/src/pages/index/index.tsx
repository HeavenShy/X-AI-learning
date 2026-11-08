/** 首页（底部“闯关”标签）：原型 01 第 2（空态）、3（已输入）、4（输入有问题）屏。等级、经验、金币登录后来自后端 */

import { Text, Textarea, View } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import { useState } from 'react'

import NavBar from '../../components/NavBar'
import { TabBarSpace, useTabSelected } from '../../components/TabPage'
import { Btn, Icon, LvChip, StatChip } from '../../components/ui'
import { estimateMinutes, formatInterrupted, INPUT_MAX_CHARS, validateInput } from '../../core/format'
import { levelOf, xpBarPercent } from '../../core/level'
import { resumeTitle } from '../../core/session'
import { TAB_INDEX } from '../../core/tabs'
import { isBareUrl, webQuizPage } from '../../core/web'
import { refreshProfile } from '../../services/account'
import { useStore } from '../../store'
import type { QuestionCount } from '../../types/api'
import './index.scss'

const TRIES = ['什么是 RAG', '复利是怎么算的', '咖啡因为什么提神', '碳中和是什么意思']
const COUNTS: QuestionCount[] = [3, 5, 10]

export default function Index() {
  const profile = useStore((s) => s.profile)
  const draft = useStore((s) => s.draft)
  const session = useStore((s) => s.session)
  const setDraft = useStore((s) => s.setDraft)
  const requestGenerate = useStore((s) => s.requestGenerate)
  const [error, setError] = useState<string | null>(null)
  const [focused, setFocused] = useState(false)

  useTabSelected(TAB_INDEX.quest)

  // 出题页因输入问题（太短 / 不合规）退回首页时，在输入框下方提示
  useDidShow(() => {
    void refreshProfile()
    const { homeError, setHomeError } = useStore.getState()
    if (homeError) {
      setError(homeError)
      setHomeError(null)
    }
  })

  const text = draft.text
  const empty = text.trim().length === 0
  const resumable = session && !session.finished ? session : null

  const onInput = (value: string) => {
    setDraft({ text: value })
    if (error) setError(null)
  }

  const onStart = () => {
    if (empty) return
    // 输入框里贴的是一个网址：转到网页出题页，链接带过去
    if (isBareUrl(text)) {
      Taro.navigateTo({ url: webQuizPage(text.trim()) })
      return
    }
    const err = validateInput(text)
    if (err) {
      setError(err)
      return
    }
    requestGenerate({ text: text.trim(), count: draft.count, difficulty: 'mixed' })
    Taro.navigateTo({ url: '/pages/generating/index' })
  }

  return (
    <View className='screen home'>
      <NavBar variant='brand' />
      <View className='content'>
        <View className='home-stats'>
          <LvChip label={levelOf(profile.xp).label} percent={xpBarPercent(profile.xp)} />
          <StatChip icon='coin'>{profile.coins}</StatChip>
        </View>

        <View className={`panel-in ${error ? 'is-error' : ''} ${focused ? 'is-focus' : ''}`}>
          <Text className='balloon'>下一话，想看懂什么？</Text>
          <Textarea
            className='panel-textarea'
            value={text}
            maxlength={INPUT_MAX_CHARS}
            placeholder='一句话、一段话都行。比如：RAG 和传统搜索有啥区别'
            placeholderClass='panel-placeholder'
            disableDefaultPadding
            onInput={(e) => onInput(e.detail.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
          />
          <View className='in-foot'>
            <View className='in-tools'>
              {/* 传文档：打开“我的知识库”上传资料后按资料出题；贴网址：用网页出题；贴视频为 P1 功能，先置灰 */}
              <View
                className='in-tool is-on'
                hoverClass='in-tool-pressed'
                onClick={() => Taro.navigateTo({ url: '/pages/kb-list/index' })}
              >
                <Icon name='docInk' />
                <Text>传文档</Text>
              </View>
              <View
                className='in-tool is-on'
                hoverClass='in-tool-pressed'
                onClick={() => Taro.navigateTo({ url: webQuizPage() })}
              >
                <Icon name='linkInk' />
                <Text>贴网址</Text>
              </View>
              <View className='in-tool'>
                <Icon name='video' />
                <Text>贴视频</Text>
              </View>
            </View>
            <Text className='in-count'>
              {Array.from(text).length} / {INPUT_MAX_CHARS}
            </Text>
          </View>
        </View>

        {error && (
          <View className='in-err'>
            <Icon name='warn' />
            <Text>{error}</Text>
          </View>
        )}

        {empty ? (
          <View className='tries'>
            <Text className='tries-title'>没想好？点一个试试</Text>
            <View className='row'>
              {TRIES.map((t) => (
                <View key={t} className='try' hoverClass='try-pressed' onClick={() => onInput(t)}>
                  {t}
                </View>
              ))}
            </View>
          </View>
        ) : (
          <View className='len'>
            {COUNTS.map((c) => (
              <View key={c} className={`len-btn ${draft.count === c ? 'is-on' : ''}`} onClick={() => setDraft({ count: c })}>
                <Text className='len-n'>{c} 题</Text>
                <Text>约 {estimateMinutes(c)} 分钟</Text>
              </View>
            ))}
          </View>
        )}

        {resumable && (
          <View className='resume' onClick={() => Taro.navigateTo({ url: '/pages/quiz/index' })}>
            <Text className='r-ep'>续</Text>
            <View className='r-text'>
              <Text className='r-title'>{resumeTitle(resumable)}</Text>
              <Text>{formatInterrupted(resumable.updatedAt, Date.now())}</Text>
            </View>
            <Text className='r-go'>继续</Text>
          </View>
        )}

        <View className='home-cta'>
          <Btn disabled={empty} onClick={onStart}>
            开始出题
          </Btn>
        </View>
      </View>
      <TabBarSpace />
    </View>
  )
}
