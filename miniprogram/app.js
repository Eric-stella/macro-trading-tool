// app.js
App({
  // 全局数据
  globalData: {
    apiBaseUrl: 'https://api.ericlovestella.cn', // 你的后端域名
    userInfo: null,
    systemInfo: null,
    isConnected: true
  },

  // 小程序初始化
  onLaunch: function() {
    console.log('宏观AI分析工具启动');
    
    // 获取系统信息
    this.getSystemInfo();
    
    // 监听网络状态
    this.monitorNetwork();
    
    // 检查登录状态
    this.checkLogin();
  },

  // 获取系统信息
  getSystemInfo: function() {
    const that = this;
    wx.getSystemInfo({
      success: function(res) {
        that.globalData.systemInfo = res;
        console.log('系统信息:', res);
      }
    });
  },

  // 监听网络状态
  monitorNetwork: function() {
    const that = this;
    
    // 获取当前网络状态
    wx.getNetworkType({
      success: function(res) {
        that.globalData.isConnected = res.networkType !== 'none';
        if (!that.globalData.isConnected) {
          wx.showToast({
            title: '网络已断开',
            icon: 'none',
            duration: 3000
          });
        }
      }
    });

    // 监听网络状态变化
    wx.onNetworkStatusChange(function(res) {
      that.globalData.isConnected = res.isConnected;
      if (!res.isConnected) {
        wx.showToast({
          title: '网络已断开',
          icon: 'none',
          duration: 3000
        });
      } else {
        wx.showToast({
          title: '网络已恢复',
          icon: 'success',
          duration: 2000
        });
      }
    });
  },

  // 检查登录状态
  checkLogin: function() {
    // 这里可以添加登录逻辑
    // 目前使用匿名访问
    console.log('当前为匿名访问模式');
  },

  // 全局方法：显示加载提示
  showLoading: function(title = '加载中...') {
    wx.showLoading({
      title: title,
      mask: true
    });
  },

  // 全局方法：隐藏加载提示
  hideLoading: function() {
    wx.hideLoading();
  },

  // 全局方法：显示提示
  showToast: function(title, icon = 'none', duration = 2000) {
    wx.showToast({
      title: title,
      icon: icon,
      duration: duration
    });
  },

  // 全局方法：显示确认对话框
  showConfirm: function(title, content, confirmText = '确定', cancelText = '取消') {
    return new Promise((resolve, reject) => {
      wx.showModal({
        title: title,
        content: content,
        confirmText: confirmText,
        cancelText: cancelText,
        success: function(res) {
          if (res.confirm) {
            resolve(true);
          } else {
            resolve(false);
          }
        },
        fail: function(err) {
          reject(err);
        }
      });
    });
  },

  // 全局方法：格式化时间
  formatTime: function(dateStr) {
    if (!dateStr) return '';
    
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    
    // 如果是一分钟内
    if (diff < 60000) {
      return '刚刚';
    }
    
    // 如果是一小时内
    if (diff < 3600000) {
      return Math.floor(diff / 60000) + '分钟前';
    }
    
    // 如果是今天
    if (date.getDate() === now.getDate() && 
        date.getMonth() === now.getMonth() && 
        date.getFullYear() === now.getFullYear()) {
      return '今天 ' + date.getHours().toString().padStart(2, '0') + ':' + 
             date.getMinutes().toString().padStart(2, '0');
    }
    
    // 如果是昨天
    const yesterday = new Date(now);
    yesterday.setDate(now.getDate() - 1);
    if (date.getDate() === yesterday.getDate() && 
        date.getMonth() === yesterday.getMonth() && 
        date.getFullYear() === yesterday.getFullYear()) {
      return '昨天 ' + date.getHours().toString().padStart(2, '0') + ':' + 
             date.getMinutes().toString().padStart(2, '0');
    }
    
    // 其他情况
    return date.getMonth() + 1 + '月' + date.getDate() + '日 ' + 
           date.getHours().toString().padStart(2, '0') + ':' + 
           date.getMinutes().toString().padStart(2, '0');
  },

  // 全局方法：获取重要性图标
  getImportanceIcon: function(level) {
    switch(level) {
      case 3:
        return '🔥'; // 高重要性
      case 2:
        return '⚠️'; // 中重要性
      case 1:
        return '📊'; // 低重要性
      default:
        return '📝';
    }
  },

  // 全局方法：获取国家旗帜emoji
  getCountryFlag: function(countryCode) {
    const flagMap = {
      'US': '🇺🇸',
      'CN': '🇨🇳',
      'EU': '🇪🇺',
      'JP': '🇯🇵',
      'GB': '🇬🇧',
      'AU': '🇦🇺',
      'CA': '🇨🇦',
      'CH': '🇨🇭',
      'DE': '🇩🇪',
      'FR': '🇫🇷'
    };
    return flagMap[countryCode] || '🌍';
  }
});