// utils/request.js
const app = getApp();

/**
 * 基础请求方法
 * @param {string} url - 请求地址（相对路径）
 * @param {string} method - 请求方法 GET/POST/PUT/DELETE
 * @param {object} data - 请求参数
 * @param {object} options - 额外配置
 * @returns {Promise} 请求Promise
 */
function request(url, method = 'GET', data = {}, options = {}) {
  return new Promise((resolve, reject) => {
    // 检查网络连接
    if (!app.globalData.isConnected) {
      app.showToast('网络连接已断开，请检查网络', 'none', 3000);
      reject(new Error('网络连接已断开'));
      return;
    }

    // 显示加载提示
    const showLoading = options.showLoading !== false;
    if (showLoading) {
      const loadingText = options.loadingText || '加载中...';
      app.showLoading(loadingText);
    }

    // 构建完整URL
    const fullUrl = app.globalData.apiBaseUrl + url;
    console.log(`[API请求] ${method} ${fullUrl}`, data);

    // 发送请求
    wx.request({
      url: fullUrl,
      method: method,
      data: data,
      header: {
        'content-type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        ...options.headers
      },
      timeout: options.timeout || 15000,
      
      success: (res) => {
        // 隐藏加载提示
        if (showLoading) {
          app.hideLoading();
        }

        console.log(`[API响应] ${method} ${url}`, res.data);

        // HTTP状态码处理
        if (res.statusCode >= 200 && res.statusCode < 300) {
          // 业务逻辑成功
          resolve(res.data);
        } else if (res.statusCode === 401) {
          // 未授权
          app.showToast('登录已过期，请重新登录', 'none');
          reject(new Error('未授权'));
        } else if (res.statusCode === 403) {
          // 禁止访问
          app.showToast('没有权限访问', 'none');
          reject(new Error('禁止访问'));
        } else if (res.statusCode === 404) {
          // 资源不存在
          app.showToast('请求的资源不存在', 'none');
          reject(new Error('资源不存在'));
        } else if (res.statusCode >= 500) {
          // 服务器错误
          app.showToast('服务器开小差了，请稍后再试', 'none');
          reject(new Error('服务器错误'));
        } else {
          // 其他错误
          app.showToast(`请求失败: ${res.statusCode}`, 'none');
          reject(new Error(`HTTP ${res.statusCode}`));
        }
      },
      
      fail: (err) => {
        // 隐藏加载提示
        if (showLoading) {
          app.hideLoading();
        }

        console.error(`[API失败] ${method} ${url}`, err);
        
        // 错误处理
        if (err.errMsg && err.errMsg.includes('timeout')) {
          app.showToast('请求超时，请检查网络', 'none');
        } else if (err.errMsg && err.errMsg.includes('fail')) {
          app.showToast('网络请求失败，请检查网络设置', 'none');
        } else {
          app.showToast('请求失败，请重试', 'none');
        }
        
        reject(err);
      },
      
      complete: () => {
        // 如果有完成回调
        if (options.complete && typeof options.complete === 'function') {
          options.complete();
        }
      }
    });
  });
}

/**
 * GET请求
 */
export const get = (url, data = {}, options = {}) => {
  return request(url, 'GET', data, options);
};

/**
 * POST请求
 */
export const post = (url, data = {}, options = {}) => {
  return request(url, 'POST', data, options);
};

/**
 * PUT请求
 */
export const put = (url, data = {}, options = {}) => {
  return request(url, 'PUT', data, options);
};

/**
 * DELETE请求
 */
export const del = (url, data = {}, options = {}) => {
  return request(url, 'DELETE', data, options);
};

/**
 * 特定API接口
 */
export const api = {
  // 获取今日事件
  getTodayEvents: (options = {}) => get('/api/events/today', {}, options),
  
  // 获取今日总结
  getTodaySummary: (options = {}) => get('/api/summary/today', {}, options),
  
  // 刷新数据
  refreshData: (options = {}) => post('/api/refresh', {}, options),
  
  // 获取服务状态
  getStatus: (options = {}) => get('/api/status', {}, options)
};

/**
 * 并发请求
 */
export const all = (requests) => {
  return Promise.all(requests);
};

/**
 * 重试请求
 */
export const retry = (fn, times = 3, delay = 1000) => {
  return new Promise((resolve, reject) => {
    const attempt = (currentTry) => {
      fn().then(resolve).catch((error) => {
        if (currentTry >= times) {
          reject(error);
        } else {
          console.log(`第${currentTry}次重试...`);
          setTimeout(() => {
            attempt(currentTry + 1);
          }, delay);
        }
      });
    };
    attempt(1);
  });
};

export default {
  get,
  post,
  put,
  del,
  api,
  all,
  retry
};