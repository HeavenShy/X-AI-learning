import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import { bootstrap } from './services/account'
import { loadDisplayFont } from './services/font'
import './app.scss'

function App({ children }: PropsWithChildren<any>) {
  useLaunch(() => {
    loadDisplayFont()
    // 微信静默登录：失败也不拦用户，出题 / 报告照常匿名可用
    void bootstrap()
  })

  // children 是将要渲染的页面
  return children
}

export default App
