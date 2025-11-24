App({
  globalData: {
    // API基础URL
    apiBaseUrl: 'http://192.168.1.145:5000/api', // 本地开发地址
    
    // 服务端状态
    serverStatus: {}
  },
  
  // 小程序启动时检查后端服务
  async onLaunch() {
    console.log('小程序启动，检查后端服务...')
    
    // #ifdef LOCAL
    // 本地开发时显示提示
    wx.showToast({
      title: '本地开发模式',
      icon: 'none'
    })
    // #endif
    
    await this.checkServerStatus()
  },
  
  // 检查服务器状态
  async checkServerStatus() {
    try {
      const res = await wx.request({
        url: this.globalData.apiBaseUrl + '/status',
        timeout: 5000
      })
      
      if (res.data.status === 'healthy') {
        console.log('后端服务正常:', res.data)
        this.globalData.serverStatus = res.data
      } else {
        console.error('后端服务异常')
        wx.showModal({
          title: '服务异常',
          content: '无法连接到后端服务，请确保本地服务已启动',
          showCancel: false
        })
      }
    } catch (error) {
      console.error('连接失败:', error)
      wx.showModal({
        title: '连接失败',
        content: '请检查：\n1. 后端服务是否运行 (python app.py)\n2. 手机和电脑是否在同一Wi-Fi\n3. 防火墙是否阻止了5000端口',
        showCancel: false
      })
    }
  }
})