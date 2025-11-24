Page({
  data: {
    event: {}
  },

  onLoad(options) {
    // 解析传递的事件数据
    if (options.event) {
      try {
        const event = JSON.parse(decodeURIComponent(options.event))
        this.setData({ 
          event,
          importanceText: this.getImportanceText(event.importance)
        })
      } catch (error) {
        console.error('解析事件数据失败:', error)
        wx.showToast({
          title: '数据错误',
          icon: 'error'
        })
      }
    }
  },

  getImportanceText(importance) {
    if (importance >= 3) return '高'
    if (importance >= 2) return '中'
    return '低'
  },

  goBack() {
    wx.navigateBack()
  }
})