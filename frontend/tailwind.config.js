/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 奢侈品设计系统 — 基于 CigarDomTabaka 设计 Token
        cream: '#FAF8F5',          // --bg 暖奶油底
        surface: '#FFFFFF',        // --surface 卡片白
        fg: '#2C2416',             // --fg 深褐黑文字
        muted: '#8A7E6E',          // --muted 次要文字
        border: '#E8E0D6',         // --border 分割线
        accent: {
          DEFAULT: '#7A1F2E',      // --accent 勃艮第红
          hover: '#5E1824',        // hover 深红
          light: '#F5EFE8',        // --accent-3 暖羊皮纸
        },
        gold: '#B87A3A',           // --accent-2 干邑金
        success: '#3D6B4F',        // --success 森林绿
      },
      fontFamily: {
        display: ['Playfair Display', 'Times New Roman', 'Georgia', 'serif'],
        body: ['-apple-system', 'BlinkMacSystemFont', 'SF Pro Text', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['SF Mono', 'ui-monospace', 'Menlo', 'monospace'],
      },
      borderRadius: {
        'sm': '4px',
        'md': '4px',
        'lg': '4px',
      },
      boxShadow: {
        'sm': '0 1px 2px rgba(44, 36, 22, 0.04)',
        'md': '0 4px 16px rgba(44, 36, 22, 0.06)',
        'lg': '0 8px 32px rgba(44, 36, 22, 0.08)',
      },
    },
  },
  plugins: [],
}
