// utils/util.js

/**
 * 格式化日期时间
 * @param {string|Date} date - 日期
 * @param {string} format - 格式，默认：yyyy-MM-dd HH:mm
 * @returns {string} 格式化后的日期
 */
const formatTime = (date, format = 'yyyy-MM-dd HH:mm') => {
  if (!date) return '';
  
  const d = date instanceof Date ? date : new Date(date);
  
  const map = {
    'M': d.getMonth() + 1, // 月份
    'd': d.getDate(), // 日
    'H': d.getHours(), // 小时
    'm': d.getMinutes(), // 分
    's': d.getSeconds(), // 秒
    'q': Math.floor((d.getMonth() + 3) / 3), // 季度
    'S': d.getMilliseconds() // 毫秒
  };
  
  return format.replace(/([yMdhHmsqS])+/g, (all, t) => {
    let v = map[t];
    if (v !== undefined) {
      if (all.length > 1) {
        v = '0' + v;
        v = v.substr(v.length - 2);
      }
      return v;
    } else if (t === 'y') {
      return (d.getFullYear() + '').substr(4 - all.length);
    }
    return all;
  });
};

/**
 * 防抖函数
 * @param {Function} fn - 需要防抖的函数
 * @param {number} delay - 延迟时间(ms)
 * @returns {Function} 防抖处理后的函数
 */
const debounce = (fn, delay = 500) => {
  let timer = null;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => {
      fn.apply(this, args);
    }, delay);
  };
};

/**
 * 节流函数
 * @param {Function} fn - 需要节流的函数
 * @param {number} interval - 间隔时间(ms)
 * @returns {Function} 节流处理后的函数
 */
const throttle = (fn, interval = 500) => {
  let lastTime = 0;
  return function(...args) {
    const now = Date.now();
    if (now - lastTime >= interval) {
      fn.apply(this, args);
      lastTime = now;
    }
  };
};

/**
 * 深度克隆对象
 * @param {Object} obj - 需要克隆的对象
 * @returns {Object} 克隆后的对象
 */
const deepClone = (obj) => {
  if (obj === null || typeof obj !== 'object') return obj;
  
  if (obj instanceof Date) {
    return new Date(obj.getTime());
  }
  
  if (obj instanceof Array) {
    return obj.reduce((arr, item, i) => {
      arr[i] = deepClone(item);
      return arr;
    }, []);
  }
  
  if (obj instanceof Object) {
    return Object.keys(obj).reduce((newObj, key) => {
      newObj[key] = deepClone(obj[key]);
      return newObj;
    }, {});
  }
};

/**
 * 生成随机ID
 * @param {number} length - ID长度
 * @returns {string} 随机ID
 */
const generateId = (length = 8) => {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
};

/**
 * 验证邮箱格式
 * @param {string} email - 邮箱地址
 * @returns {boolean} 是否有效
 */
const isValidEmail = (email) => {
  const reg = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return reg.test(email);
};

/**
 * 验证手机号格式
 * @param {string} phone - 手机号
 * @returns {boolean} 是否有效
 */
const isValidPhone = (phone) => {
  const reg = /^1[3-9]\d{9}$/;
  return reg.test(phone);
};

/**
 * 格式化货币数字
 * @param {number} num - 数字
 * @param {number} decimals - 小数位数
 * @returns {string} 格式化后的货币
 */
const formatCurrency = (num, decimals = 2) => {
  if (isNaN(num)) return '0.00';
  
  const fixedNum = Number(num).toFixed(decimals);
  const parts = fixedNum.split('.');
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return parts.join('.');
};

/**
 * 存储数据到本地
 * @param {string} key - 键名
 * @param {any} data - 数据
 */
const setStorage = (key, data) => {
  try {
    wx.setStorageSync(key, data);
  } catch (e) {
    console.error('存储数据失败:', e);
  }
};

/**
 * 从本地获取数据
 * @param {string} key - 键名
 * @returns {any} 数据
 */
const getStorage = (key) => {
  try {
    return wx.getStorageSync(key);
  } catch (e) {
    console.error('获取数据失败:', e);
    return null;
  }
};

/**
 * 从本地移除数据
 * @param {string} key - 键名
 */
const removeStorage = (key) => {
  try {
    wx.removeStorageSync(key);
  } catch (e) {
    console.error('移除数据失败:', e);
  }
};

/**
 * 检查对象是否为空
 * @param {Object} obj - 对象
 * @returns {boolean} 是否为空
 */
const isEmptyObject = (obj) => {
  return Object.keys(obj).length === 0 && obj.constructor === Object;
};

export {
  formatTime,
  debounce,
  throttle,
  deepClone,
  generateId,
  isValidEmail,
  isValidPhone,
  formatCurrency,
  setStorage,
  getStorage,
  removeStorage,
  isEmptyObject
};