/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 极简黑金 — accent: 古铜金 #A16207
        gold: {
          50: '#fef7ed',
          100: '#fcedd5',
          200: '#f8d7a3',
          300: '#f4c064',
          400: '#d4a24e',
          500: '#a16207',
          600: '#7c4c05',
          700: '#5e3904',
        },
        // 设计规范配色 — 基于 design-spec.md
        brand: {
          brown: '#8B6914',             // 品牌棕：标题、图表线、Tab选中态
          gold: '#D4AF37',              // 金色：当前价格高亮
          'tab-active': '#F5F0E6',      // Tab/按钮选中底色
        },
        // 暖白底色
        cream: '#FAFAF9',
        // 石色 — 取代旧brown色系
        stone: {
          50: '#FAFAF9',
          100: '#F5F5F4',
          200: '#E7E5E4',
          300: '#D6D3D1',
          400: '#A8A29E',
          500: '#78716C',
          600: '#57534E',
          700: '#44403C',
          800: '#292524',
          900: '#1C1917',
        },
      },
      fontFamily: {
        serif: ['Georgia', 'Noto Serif SC', 'serif'],
      },
      borderRadius: {
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
      },
      boxShadow: {
        'sm': '0 1px 3px rgba(12,10,9,0.06)',
        'md': '0 4px 16px rgba(12,10,9,0.08)',
        'lg': '0 8px 32px rgba(12,10,9,0.10)',
      },
    },
  },
  plugins: [],
}
