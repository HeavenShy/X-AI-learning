/**
 * 加载漫画标题字体（站酷庆科黄油体 GB2312 一级字库子集，由后端 /static/fonts 提供）。
 * scopes 默认包含 native，Canvas 2D 海报也能用；加载失败时 CSS 自动退回系统粗体。
 */

import Taro from '@tarojs/taro'

import { API_BASE } from './request'

export const DISPLAY_FONT = 'ZCOOL QingKe HuangYou'
export const FONT_URL = `${API_BASE}/static/fonts/zcool-qingke-huangyou-gb1.woff`

let ready: Promise<boolean> | null = null

export function loadDisplayFont(): Promise<boolean> {
  if (!ready) {
    ready = Taro.loadFontFace({
      global: true,
      family: DISPLAY_FONT,
      source: `url("${FONT_URL}")`,
      // 微信官方类型里有 scopes（webview / native / skyline），Taro 类型未声明
      ...({ scopes: ['webview', 'native'] } as object)
    })
      .then(() => true)
      .catch((err) => {
        console.warn('[font] 漫画字体加载失败，使用系统字体', err)
        return false
      })
  }
  return ready
}
