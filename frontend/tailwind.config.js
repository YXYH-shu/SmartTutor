/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // —— 保留现有 primary 蓝色色阶（业务组件仍在用） ——
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a',
          950: '#172554',
        },
        // —— Token-driven 语义色（用 RGB channel 形式,支持 /opacity modifier） ——
        'bg-base': 'rgb(var(--color-bg-base-rgb) / <alpha-value>)',
        'bg-elevated': 'rgb(var(--color-bg-elevated-rgb) / <alpha-value>)',
        'text-primary': 'rgb(var(--color-text-primary-rgb) / <alpha-value>)',
        'text-secondary': 'rgb(var(--color-text-secondary-rgb) / <alpha-value>)',
        'text-tertiary': 'rgb(var(--color-text-tertiary-rgb) / <alpha-value>)',
        'border-subtle': 'rgb(var(--color-border-subtle-rgb) / <alpha-value>)',
        'border-strong': 'rgb(var(--color-border-strong-rgb) / <alpha-value>)',
        accent: 'rgb(var(--color-accent-rgb) / <alpha-value>)',
        'accent-soft': 'var(--color-accent-soft)',
        'status-success': 'rgb(var(--color-status-success-rgb) / <alpha-value>)',
        'status-warning': 'rgb(var(--color-status-warning-rgb) / <alpha-value>)',
        'status-info': 'rgb(var(--color-status-info-rgb) / <alpha-value>)',
        'status-error': 'rgb(var(--color-status-error-rgb) / <alpha-value>)',
      },
      fontFamily: {
        display: ['Inter Display', 'Inter', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'IBM Plex Mono', 'monospace'],
      },
      fontSize: {
        '11': ['11px', { lineHeight: '16px', letterSpacing: '0.01em' }],
        '12': ['12px', { lineHeight: '18px' }],
        '14': ['14px', { lineHeight: '20px' }],
        '16': ['16px', { lineHeight: '24px' }],
        '18': ['18px', { lineHeight: '26px' }],
        '24': ['24px', { lineHeight: '32px', letterSpacing: '-0.02em' }],
        '32': ['32px', { lineHeight: '40px', letterSpacing: '-0.02em' }],
      },
      borderRadius: {
        // 保留消息气泡圆角
        'msg-user': '16px 16px 4px 16px',
        'msg-ai': '16px 16px 16px 4px',
        // Token-driven 圆角
        sm: '6px',
        md: '8px',
        lg: '10px',
        xl: '12px',
      },
      borderWidth: {
        // 方案要求分隔线 0.5px(Retina 屏 = 1 物理像素)。
        // 只影响显式 `border` 类;不带 border 类的元素 border-width 默认仍是 0(Tailwind preflight)。
        DEFAULT: '0.5px',
        '0': '0',
        '2': '2px',
        '4': '4px',
        '8': '8px',
      },
      boxShadow: {
        '1': 'var(--elevation-1)',
        '2': 'var(--elevation-2)',
        '3': 'var(--elevation-3)',
        '4': 'var(--elevation-4)',
        hero: 'var(--shadow-hero)',
      },
      transitionTimingFunction: {
        out: 'var(--ease-out)',
        spring: 'var(--ease-spring)',
        standard: 'var(--ease-standard)',
      },
      animation: {
        'bounce-dot': 'bounce-dot 1.4s infinite ease-in-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fade-in 0.5s ease-out forwards',
        'fade-in-up': 'fade-in-up 0.5s ease-out forwards',
        'slide-in-right': 'slide-in-right 0.3s ease-out forwards',
        'scale-in': 'scale-in 0.3s ease-out forwards',
      },
      keyframes: {
        'bounce-dot': {
          '0%, 80%, 100%': { transform: 'scale(0)' },
          '40%': { transform: 'scale(1)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in-right': {
          '0%': { opacity: '0', transform: 'translateX(20px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
};
