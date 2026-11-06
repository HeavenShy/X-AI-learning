/** 知识库名称弹窗：新建与改名共用。本地先按后端同规则校验，提交失败（如名称不合规、已达上限）在框下提示 */

import { Input, Text, View } from '@tarojs/components'
import { useState } from 'react'

import { cleanKbName, KB_NAME_MAX, validateKbName } from '../core/kb'
import { ApiError } from '../services/request'
import { Btn, Icon } from './ui'

interface Props {
  title: string
  initial?: string
  confirm: string
  /** 返回 Promise：成功后由调用方关闭弹窗；抛出的 ApiError 文案显示在输入框下方 */
  onSubmit: (name: string) => Promise<void>
  onClose: () => void
}

export default function KbNameDialog({ title, initial = '', confirm, onSubmit, onClose }: Props) {
  const [value, setValue] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    if (saving) return
    const err = validateKbName(value)
    if (err) {
      setError(err)
      return
    }
    const name = cleanKbName(value)
    if (name === initial) {
      onClose()
      return
    }
    setSaving(true)
    try {
      await onSubmit(name)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '没保存上，稍后再试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <View className='scrim' catchMove>
      <View className='dialog kb-name-dialog'>
        <Text className='d-title'>{title}</Text>
        <Text className='d-text'>比如“公司新人考核”“PMP 备考”，只有你自己能看到。</Text>
        <View className={`input ${error ? 'is-error' : ''}`}>
          <Input
            className='input-el'
            value={value}
            maxlength={KB_NAME_MAX + 10}
            placeholder={`知识库名称，最多 ${KB_NAME_MAX} 个字`}
            focus
            confirmType='done'
            onInput={(e) => {
              setValue(e.detail.value)
              if (error) setError(null)
            }}
            onConfirm={() => void submit()}
          />
        </View>
        {error && (
          <View className='kb-err'>
            <Icon name='warn' />
            <Text>{error}</Text>
          </View>
        )}
        <View className='row'>
          <Btn disabled={saving} onClick={() => void submit()}>
            {saving ? '保存中' : confirm}
          </Btn>
          <Btn kind='ghost' onClick={onClose}>
            取消
          </Btn>
        </View>
      </View>
    </View>
  )
}
