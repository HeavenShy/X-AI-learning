export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/generating/index',
    'pages/overview/index',
    'pages/quiz/index',
    'pages/clear/index',
    'pages/report/index',
    'pages/poster/index',
    'pages/me/index',
    'pages/review/index',
    'pages/review-answer/index',
    'pages/history/index',
    'pages/stats/index',
    'pages/knowledge-tree/index',
    'pages/kb-list/index',
    'pages/kb-detail/index',
    'pages/kb-quiz/index',
    'pages/web-quiz/index',
    'pages/video-quiz/index'
  ],
  // 原型的标签栏样式（漫画字体、粗上边框、黄色填充图标）原生 tabBar 画不出来，用自定义 tabBar（src/custom-tab-bar）。
  // list 仍需完整填写：决定哪些页面是标签页（只能用 switchTab / reLaunch 打开）
  tabBar: {
    custom: true,
    color: '#5E6670',
    selectedColor: '#000000',
    backgroundColor: '#FFFFFF',
    borderStyle: 'black',
    list: [
      { pagePath: 'pages/index/index', text: '闯关' },
      { pagePath: 'pages/review/index', text: '复习' },
      { pagePath: 'pages/me/index', text: '我的' }
    ]
  },
  window: {
    // 原型的导航栏是自定义的（品牌字、✕ 按钮），所有页面统一用自定义导航
    navigationStyle: 'custom',
    navigationBarTextStyle: 'black',
    backgroundColor: '#EEF0F2',
    backgroundTextStyle: 'dark'
  }
})
