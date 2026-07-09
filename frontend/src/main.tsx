import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { useUIStore } from './stores/uiStore';
import './styles/globals.css';

// 启动时把持久化的 theme 应用到 <html data-theme>，确保 CSS 变量立即生效
useUIStore.getState().setTheme(useUIStore.getState().theme);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
