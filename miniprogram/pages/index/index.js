const api = require('../../utils/api')

Page({
  data: {
    events: [],
    summary: '',
    loading: true,
    isRefreshing: false,
    lastUpdated: '',
    serverStatus: {}
  },

  // 页面加载
  async onLoad() {
    // 获取全局数据
    this.setData({
      serverStatus: getApp().globalData.serverStatus
    })
    
    await this.loadData()
  },

  // 加载数据
  async loadData() {
    this.setData({ loading: true })
    
    try {
      // 并行获取事件和总结
      const [eventsRes, summaryRes] = await Promise.all([
        api.getTodayEvents(),
        api.getTodaySummary()
      ])

      this.setData({
        events: eventsRes.data || [],
        summary: summaryRes.summary || '暂无总结',
        lastUpdated: new Date().toLocaleString('zh-HK'),
        loading: false
      })

      // 缓存到本地（用于离线查看）
      wx.setStorageSync('cached_events', eventsRes.data || [])
      wx.setStorageSync('cached_summary', summaryRes.summary || '')

    } catch (error) {
      console.error('加载失败:', error)
      
      // 加载缓存数据
      const cachedEvents = wx.getStorageSync('cached_events') || []
      const cachedSummary = wx.getStorageSync('cached_summary') || ''
      
      this.setData({
        events: cachedEvents,
        summary: cachedSummary,
        loading: false
      })
      
      wx.showToast({
        title: '加载失败，使用缓存数据',
        icon: 'none',
        duration: 3000
      })
    }
  },

  // 下拉刷新
  async onRefresh() {
    this.setData({ isRefreshing: true })
    await this.loadData()
    
    // 延迟关闭刷新状态，让用户看到效果
    setTimeout(() => {
      this.setData({ isRefreshing: false })
      wx.showToast({
        title: '刷新成功',
        icon: 'success'
      })
    }, 1000)
  },

  // 手动刷新按钮
  async refreshAll() {
    wx.showLoading({ title: '刷新中...' })
    
    try {
      await api.refreshData()
      await this.loadData()
      wx.showToast({
        title: '数据已更新',
        icon: 'success'
      })
    } catch (error) {
      wx.showToast({
        title: '刷新失败',
        icon: 'error'
      })
    } finally {
      wx.hideLoading()
    }
  },

  // 跳转到详情页
  goToDetail(e) {
    const event = e.currentTarget.dataset.event
    wx.navigateTo({
      url: `/pages/detail/detail?event=${encodeURIComponent(JSON.stringify(event))}`
    })
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.onRefresh()
    wx.stopPullDownRefresh()
  }
})