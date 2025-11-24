/**
 * API请求封装
 * 支持本地开发和生产环境
 */

const app = getApp()

// 请求超时时间
const REQUEST_TIMEOUT = 10000

// 通用请求函数
function request(url, method = 'GET', data = {}, options = {}) {
  return new Promise((resolve, reject) => {
    const fullUrl = app.globalData.apiBaseUrl + url
    
    console.log(`${method} ${fullUrl}`, data)
    
    wx.request({
      url: fullUrl,
      method,
      data,
      timeout: options.timeout || REQUEST_TIMEOUT,
      header: {
        'content-type': 'application/json'
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          // 请求成功
          if (res.data && res.data.status === 'success') {
            resolve(res.data)
          } else {
            // 没有status字段，直接返回数据
            resolve(res.data)
          }
        } else {
          // HTTP错误
          console.error('HTTP错误:', res)
          reject({
            code: res.statusCode,
            message: res.data?.message || '服务器错误'
          })
        }
      },
      fail: (err) => {
        // 网络错误
        console.error('网络错误:', err)
        
        // 显示错误提示
        wx.showToast({
          title: '网络连接失败',
          icon: 'error',
          duration: 2000
        })
        
        reject({
          code: 'NETWORK_ERROR',
          message: '请检查网络连接和本地服务'
        })
      }
    })
  })
}

// API接口
module.exports = {
  // 获取今日事件
  getTodayEvents() {
    return request('/events/today')
  },
  
  // 获取每日总结
  getTodaySummary() {
    return request('/summary/today')
  },
  
  // 刷新数据
  refreshData() {
    return request('/refresh', 'POST')
  },
  
  // 获取服务器状态
  getServerStatus() {
    return request('/status')
  }
}