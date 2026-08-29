import axios from 'axios';
import router from '@/router'; // 稍后配置

const http = axios.create({
  baseURL: '/api',
  timeout: 10000,
});

// 请求拦截器：自动添加 token
http.interceptors.request.use(config => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, error => Promise.reject(error));

// 响应拦截器：处理 401 错误
http.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      router.push('/login');
    }
    return Promise.reject(error);
  }
);

export default http;