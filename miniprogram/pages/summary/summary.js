// pages/summary/summary.js
import { api } from '../../utils/request.js';
import { formatTime } from '../../utils/util.js';
const app = getApp();

Page({
  /**
   * 页面的初始数据
   */
  data: {
    // 总结数据
    summary: '',
    formattedSummary: '',
    
    // 页面状态
    isLoading: true,
    isRefreshing: false,
    loadError: false,
    
    // 服务器信息
    serverInfo: {
      lastUpdated: '',
      aiEnabled: false
    },
    
    // 展开的章节
    expandedSections: {
      market: true,
      events: true,
      outlook: true,
      strategy: true
    },
    
    // 分析统计
    analysisStats: {
      totalEvents: 0,
      highImpact: 0,
      marketSentiment: '中性'
    }
  },

  /**
   * 生命周期函数--监听页面加载
   */
  onLoad: function(options) {
    console.log('总结页加载');
    this.loadSummaryData();
  },

  /**
   * 加载总结数据
   */
  loadSummaryData: async function() {
    try {
      this.setData({ isLoading: true, loadError: false });
      
      // 并行获取总结和事件数据
      const [summaryRes, eventsRes] = await Promise.all([
        api.getTodaySummary({ showLoading: false }),
        api.getTodayEvents({ showLoading: false })
      ]);
      
      // 处理总结数据
      if (summaryRes.status === 'success') {
        const formatted = this.formatSummary(summaryRes.summary);
        this.setData({
          summary: summaryRes.summary,
          formattedSummary: formatted,
          'serverInfo.lastUpdated': summaryRes.generated_at || ''
        });
      }
      
      // 处理事件数据用于统计
      if (eventsRes.status === 'success') {
        this.calculateStats(eventsRes.data);
      }
      
      // 获取服务器状态
      const statusRes = await api.getStatus({ showLoading: false });
      if (statusRes) {
        this.setData({
          'serverInfo.aiEnabled': statusRes.ai_enabled || false
        });
      }
      
    } catch (error) {
      console.error('加载总结数据失败:', error);
      this.setData({ loadError: true });
      app.showToast('加载总结失败', 'none');
      
      // 显示默认数据
      this.setData({
        summary: '【模拟数据】今日市场相对平静，关注欧美经济数据发布。',
        formattedSummary: this.formatSummary('【模拟数据】今日市场相对平静，关注欧美经济数据发布。'),
        isLoading: false
      });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  /**
   * 格式化总结文本
   */
  formatSummary: function(summary) {
    if (!summary) return '';
    
    // 分割成段落
    const paragraphs = summary.split('\n').filter(p => p.trim());
    
    // 识别章节并添加样式
    const formatted = paragraphs.map(paragraph => {
      // 检查是否是标题
      if (paragraph.includes('市场主线') || 
          paragraph.includes('焦点事件') || 
          paragraph.includes('主要货币对展望') || 
          paragraph.includes('今日策略')) {
        return {
          type: 'title',
          content: paragraph,
          icon: this.getSectionIcon(paragraph)
        };
      }
      
      // 检查是否是列表项
      if (paragraph.startsWith('•') || paragraph.startsWith('○') || paragraph.includes(':')) {
        return {
          type: 'list',
          content: paragraph
        };
      }
      
      // 普通段落
      return {
        type: 'paragraph',
        content: paragraph
      };
    });
    
    return formatted;
  },

  /**
   * 获取章节图标
   */
  getSectionIcon: function(sectionTitle) {
    if (sectionTitle.includes('市场主线')) return '📈';
    if (sectionTitle.includes('焦点事件')) return '🔥';
    if (sectionTitle.includes('货币对展望')) return '💱';
    if (sectionTitle.includes('今日策略')) return '🎯';
    return '📝';
  },

  /**
   * 计算统计信息
   */
  calculateStats: function(events) {
    if (!events || !Array.isArray(events)) return;
    
    const highImpact = events.filter(event => event.importance === 3).length;
    
    // 简单情感分析（根据高影响事件数量）
    let sentiment = '中性';
    if (highImpact >= 3) sentiment = '高波动';
    else if (highImpact === 0) sentiment = '平静';
    
    this.setData({
      'analysisStats.totalEvents': events.length,
      'analysisStats.highImpact': highImpact,
      'analysisStats.marketSentiment': sentiment
    });
  },

  /**
   * 刷新数据
   */
  refreshData: async function() {
    if (this.data.isRefreshing) return;
    
    this.setData({ isRefreshing: true });
    wx.showNavigationBarLoading();
    
    try {
      // 触发后端刷新
      await api.refreshData();
      
      // 重新加载数据
      await this.loadSummaryData();
      
      app.showToast('总结已刷新', 'success');
      
    } catch (error) {
      console.error('刷新失败:', error);
      app.showToast('刷新失败', 'none');
    } finally {
      this.setData({ isRefreshing: false });
      wx.hideNavigationBarLoading();
    }
  },

  /**
   * 切换章节展开状态
   */
  toggleSection: function(e) {
    const section = e.currentTarget.dataset.section;
    const key = `expandedSections.${section}`;
    this.setData({
      [key]: !this.data.expandedSections[section]
    });
  },

  /**
   * 复制总结到剪贴板
   */
  copySummary: function() {
    wx.setClipboardData({
      data: this.data.summary,
      success: () => {
        app.showToast('已复制到剪贴板', 'success');
      }
    });
  },

  /**
   * 分享总结
   */
  shareSummary: function() {
    wx.showShareMenu({
      withShareTicket: true
    });
  },

  /**
   * 用户点击右上角分享
   */
  onShareAppMessage: function() {
    return {
      title: '今日外汇市场AI分析总结',
      path: '/pages/summary/summary',
      imageUrl: '/images/summary_share.png'
    };
  },

  /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh: function() {
    this.refreshData();
  }
});