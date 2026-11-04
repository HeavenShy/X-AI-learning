import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'

import { loadDisplayFont } from './services/font'
import './app.scss'

function App({ children }: PropsWithChildren<any>) {
  useLaunch(() => {
    loadDisplayFont()
  })

  // children 是将要渲染的页面
  return children
}

export default App
