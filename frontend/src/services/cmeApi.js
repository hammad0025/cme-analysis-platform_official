import axios from 'axios';

const DEV_MODE = process.env.REACT_APP_DEV_MODE === 'true';
const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://g4dzem9rtk.execute-api.us-east-1.amazonaws.com/prod';

const cmeApi = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  // 20s default keeps the UI responsive when the API is unreachable in dev.
  timeout: DEV_MODE ? 20000 : 60000,
});

cmeApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

cmeApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !DEV_MODE) {
      localStorage.removeItem('auth_token');
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  },
);

export default cmeApi;




