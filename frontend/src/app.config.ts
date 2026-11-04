export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/generating/index',
    'pages/overview/index',
    'pages/quiz/index',
    'pages/clear/index',
    'pages/report/index',
    'pages/poster/index'
  ],
  window: {
    // 原型的导航栏是自定义的（品牌字、✕ 按钮），所有页面统一用自定义导航
    navigationStyle: 'custom',
    navigationBarTextStyle: 'black',
    backgroundColor: '#EEF0F2',
    backgroundTextStyle: 'dark'
  }
})
