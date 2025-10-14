// docs/nuxt.config.js
export default {
  extends: ['docus'],
  app: {
    baseURL: '/veadk-python/'
  },
  image: {
    provider: 'none' // 禁用 IPX 图片优化
  }
}