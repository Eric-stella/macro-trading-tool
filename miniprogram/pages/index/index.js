// pages/index/index.js
import { api } from '../../utils/request.js';
import { formatTime, debounce } from '../../utils/util.js';
const app = getApp();

Page({
  /**
   * 页面的初始数据
   */
  data: {
    // 事件列表
    events: [],
    
    // 筛选后的列表
    filteredEvents: [],
    
    // 筛选条件
    filters: {
      importance: 'all', // all, high, medium, low
      currency: 'all', // all, USD, EUR, CNY...
      country: 'all' // all, US, CN, EU...
    },
    
    // 排序方式
    sortBy: 'time', // time, importance, country
    
    // 页面状态
    isLoading: true,
    isRefreshing: false,
    hasMore: false,
    loadError: false,
    
    // 服务器信息
    serverInfo: {
      lastUpdated: '',
      mode: '',
      eventsCount: 0,
      aiEnabled: false
    },
    
    // 当前时间
    currentTime: '',
    
    // 下拉刷新状态
    pullDownStatus: 'default',
    
    // 筛选器可见性
    showFilters: false,
    
    // 可用筛选选项
    filterOptions: {
      importance: [
        { label: '全部', value: 'all' },
        { label: '🔥 高重要性', value: 'high' },
        { label: '⚠️ 中重要性', value: 'medium' },
        { label: '📊 低重要性', value: 'low' }
      ],
      currency: [
        { label: '全部货币', value: 'all' },
        { label: '🇺🇸 美元', value: 'USD' },
        { label: '🇪🇺 欧元', value: 'EUR' },
        { label: '🇨🇳 人民币', value: 'CNY' },
        { label: '🇯🇵 日元', value: 'JPY' },
        { label: '🇬🇧 英镑', value: 'GBP' }
      ]
    },
    
    // 页面配置
    pageConfig: {
      pageSize: 20,
      currentPage: 1,
      totalPages: 1
    }
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad: function(options) {
    console.log('首页加载，参数:', options);
    
    // 初始化数据
    this.initData();
    
    // 开始加载数据
    this.loadInitialData();
    
    // 启动时钟
    this.startClock();
  },

  /**
   * 生命周期函数--监听页面显示
   */
  onShow: function() {
    // 检查是否需要刷新
    const lastUpdateTime = getApp().globalData.lastUpdateTime;
    if (lastUpdateTime && Date.now() - lastUpdateTime > 5 * 60 * 1000) {
      this.refreshData();
    }
  },

  /**
   * 初始化数据
   */
  initData: function() {
    // 从缓存加载筛选设置
    const savedFilters = wx.getStorageSync('event_filters') || {};
    if (savedFilters) {
      this.setData({
        'filters.importance': savedFilters.importance || 'all',
        'filters.currency': savedFilters.currency || 'all',
        'filters.country': savedFilters.country || 'all'
      });
    }
  },

  /**
   * 加载初始数据
   */
  loadInitialData: async function() {
    try {
      this.setData({ isLoading: true, loadError: false });
      
      // 并行请求数据
      const [eventsRes, statusRes] = await Promise.all([
        api.getTodayEvents({ showLoading: false }),
        api.getStatus({ showLoading: false })
      ]);
      
      // 处理事件数据
      if (eventsRes.status === 'success') {
        const events = this.processEvents(eventsRes.data);
        this.setData({
          events: events,
          filteredEvents: this.applyFilters(events),
          'serverInfo.eventsCount': events.length,
          'serverInfo.mode': eventsRes.mode || 'unknown',
          'serverInfo.lastUpdated': eventsRes.generated_at || ''
        });
        
        // 更新全局最后更新时间
        getApp().globalData.lastUpdateTime = Date.now();
      }
      
      // 处理状态数据
      if (statusRes) {
        this.setData({
          'serverInfo.aiEnabled': statusRes.ai_enabled || false,
          'serverInfo.mode': statusRes.mode || this.data.serverInfo.mode
        });
      }
      
    } catch (error) {
      console.error('加载数据失败:', error);
      this.setData({ loadError: true });
      app.showToast('数据加载失败，请稍后重试', 'none');
      
      // 显示缓存数据
      const cachedEvents = wx.getStorageSync('cached_events') || [];
      if (cachedEvents.length > 0) {
        this.setData({
          events: cachedEvents,
          filteredEvents: cachedEvents,
          'serverInfo.eventsCount': cachedEvents.length,
          'serverInfo.lastUpdated': '缓存数据'
        });
      }
    } finally {
      this.setData({ isLoading: false });
    }
  },

  /**
   * 处理事件数据
   */
  processEvents: function(events) {
    return events.map(event => {
      // 确保所有必要字段
      const processed = {
        id: event.id || this.generateEventId(event),
        time: event.time || '00:00',
        country: event.country || 'Unknown',
        name: event.name || '未命名事件',
        forecast: event.forecast || 'N/A',
        previous: event.previous || 'N/A',
        actual: event.actual || null,
        importance: event.importance || 1,
        currency: event.currency || 'USD',
        ai_analysis: event.ai_analysis || '暂无分析数据',
        isExpanded: false // 控制AI分析展开
      };
      
      // 添加显示字段
      processed.displayTime = this.formatDisplayTime(processed.time);
      processed.flag = app.getCountryFlag(processed.country);
      processed.importanceIcon = app.getImportanceIcon(processed.importance);
      processed.importanceText = this.getImportanceText(processed.importance);
      processed.importanceClass = this.getImportanceClass(processed.importance);
      processed.hasActual = processed.actual !== null;
      processed.actualClass = this.getActualClass(processed.actual, processed.forecast);
      
      return processed;
    });
  },

  /**
   * 生成事件ID
   */
  generateEventId: function(event) {
    const str = `${event.time}-${event.country}-${event.name}`;
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = ((hash << 5) - hash) + str.charCodeAt(i);
      hash |= 0; // 转换为32位整数
    }
    return Math.abs(hash).toString(16);
  },

  /**
   * 格式化显示时间
   */
  formatDisplayTime: function(timeStr) {
    if (!timeStr) return '--:--';
    
    // 如果是完整时间戳
    if (timeStr.includes(':')) {
      const [hours, minutes] = timeStr.split(':').map(Number);
      return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
    }
    
    return timeStr;
  },

  /**
   * 获取重要性文本
   */
  getImportanceText: function(level) {
    switch(level) {
      case 3: return '高';
      case 2: return '中';
      case 1: return '低';
      default: return '未知';
    }
  },

  /**
   * 获取重要性样式类
   */
  getImportanceClass: function(level) {
    switch(level) {
      case 3: return 'importance-high';
      case 2: return 'importance-medium';
      case 1: return 'importance-low';
      default: return '';
    }
  },

  /**
   * 获取实际值样式类
   */
  getActualClass: function(actual, forecast) {
    if (actual === null || forecast === 'N/A') return '';
    
    try {
      const actualNum = parseFloat(actual);
      const forecastNum = parseFloat(forecast);
      
      if (isNaN(actualNum) || isNaN(forecastNum)) return '';
      
      if (actualNum > forecastNum) return 'actual-better';
      if (actualNum < forecastNum) return 'actual-worse';
      return 'actual-equal';
    } catch (e) {
      return '';
    }
  },

  /**
   * 应用筛选条件
   */
  applyFilters: function(events) {
    const { filters } = this.data;
    let filtered = [...events];
    
    // 按重要性筛选
    if (filters.importance !== 'all') {
      filtered = filtered.filter(event => {
        if (filters.importance === 'high') return event.importance === 3;
        if (filters.importance === 'medium') return event.importance === 2;
        if (filters.importance === 'low') return event.importance === 1;
        return true;
      });
    }
    
    // 按货币筛选
    if (filters.currency !== 'all') {
      filtered = filtered.filter(event => event.currency === filters.currency);
    }
    
    // 按国家筛选
    if (filters.country !== 'all') {
      filtered = filtered.filter(event => event.country === filters.country);
    }
    
    // 排序
    filtered.sort((a, b) => {
      switch (this.data.sortBy) {
        case 'time':
          return this.compareTime(a.time, b.time);
        case 'importance':
          return b.importance - a.importance;
        case 'country':
          return a.country.localeCompare(b.country);
        default:
          return 0;
      }
    });
    
    return filtered;
  },

  /**
   * 比较时间
   */
  compareTime: function(timeA, timeB) {
    const [hoursA, minutesA] = timeA.split(':').map(Number);
    const [hoursB, minutesB] = timeB.split(':').map(Number);
    
    if (hoursA !== hoursB) return hoursA - hoursB;
    return minutesA - minutesB;
  },

  /**
   * 刷新数据
   */
  refreshData: async function() {
    if (this.data.isRefreshing) return;
    
    this.setData({ isRefreshing: true });
    
    try {
      // 显示刷新动画
      wx.showNavigationBarLoading();
      
      // 触发后端刷新
      await api.refreshData();
      
      // 重新加载数据
      await this.loadInitialData();
      
      app.showToast('刷新成功', 'success');
      
    } catch (error) {
      console.error('刷新失败:', error);
      app.showToast('刷新失败，请重试', 'none');
    } finally {
      this.setData({ isRefreshing: false });
      wx.hideNavigationBarLoading();
      wx.stopPullDownRefresh();
    }
  },

  /**
   * 手动刷新按钮事件
   */
  onRefreshTap: debounce(function() {
    this.refreshData();
  }, 1000),

  /**
   * 切换事件展开状态
   */
  onToggleExpand: function(e) {
    const index = e.currentTarget.dataset.index;
    const event = this.data.filteredEvents[index];
    
    if (!event) return;
    
    const key = `filteredEvents[${index}].isExpanded`;
    this.setData({
      [key]: !event.isExpanded
    });
    
    // 收起其他展开的事件
    this.data.filteredEvents.forEach((item, i) => {
      if (i !== index && item.isExpanded) {
        this.setData({
          [`filteredEvents[${i}].isExpanded`]: false
        });
      }
    });
  },

  /**
   * 切换筛选器可见性
   */
  onToggleFilters: function() {
    this.setData({
      showFilters: !this.data.showFilters
    });
  },

  /**
   * 筛选条件变更
   */
  onFilterChange: function(e) {
    const { type } = e.currentTarget.dataset;
    const { value } = e.detail;
    
    this.setData({
      [`filters.${type}`]: value
    });
    
    // 保存筛选设置
    wx.setStorageSync('event_filters', this.data.filters);
    
    // 应用筛选
    this.applyFiltersAndUpdate();
  },

  /**
   * 排序方式变更
   */
  onSortChange: function(e) {
    const sortBy = e.currentTarget.dataset.sort;
    this.setData({ sortBy });
    
    // 应用筛选和排序
    this.applyFiltersAndUpdate();
  },

  /**
   * 应用筛选并更新视图
   */
  applyFiltersAndUpdate: function() {
    const filteredEvents = this.applyFilters(this.data.events);
    this.setData({ filteredEvents });
  },

  /**
   * 重置筛选条件
   */
  onResetFilters: function() {
    this.setData({
      'filters.importance': 'all',
      'filters.currency': 'all',
      'filters.country': 'all',
      sortBy: 'time'
    });
    
    wx.removeStorageSync('event_filters');
    
    this.applyFiltersAndUpdate();
    app.showToast('筛选条件已重置', 'success');
  },

  /**
   * 启动时钟
   */
  startClock: function() {
    const updateTime = () => {
      const now = new Date();
      const timeStr = formatTime(now, 'HH:mm:ss');
      this.setData({ currentTime: timeStr });
    };
    
    updateTime();
    this.clockInterval = setInterval(updateTime, 1000);
  },

  /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh: function() {
    this.refreshData();
  },

  /**
   * 页面上拉触底事件的处理函数
   */
  onReachBottom: function() {
    // 如果需要分页可以在这里实现
    console.log('触底');
  },

  /**
   * 用户点击右上角分享
   */
  onShareAppMessage: function() {
    return {
      title: '宏观AI分析工具 - 专业外汇市场分析',
      path: '/pages/index/index',
      imageUrl: '/images/share.png'
    };
  },

  /**
   * 用户点击右上角分享到朋友圈
   */
  onShareTimeline: function() {
    return {
      title: '宏观AI分析工具 - 实时经济事件分析',
      query: ''
    };
  },

  /**
   * 页面卸载
   */
  onUnload: function() {
    if (this.clockInterval) {
      clearInterval(this.clockInterval);
    }
    
    // 缓存数据
    if (this.data.events.length > 0) {
      wx.setStorageSync('cached_events', this.data.events);
    }
  }
});