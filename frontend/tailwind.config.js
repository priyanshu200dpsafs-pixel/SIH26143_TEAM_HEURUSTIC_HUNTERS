/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#060a12',
          900: '#0a101d',
          800: '#0f172a',
          700: '#1e293b',
          600: '#334155',
        },
        radar: {
          cyan: '#06b6d4',
          emerald: '#10b981',
          amber: '#f59e0b',
          rose: '#f43f5e',
        },
        m: {
          bg:        '#F5F7FA',
          card:      '#FFFFFF',
          surface:   '#F8FAFC',
          border:    '#E2E8F0',
          divider:   '#CBD5E1',
          primary:   '#0F172A',
          secondary: '#64748B',
          muted:     '#94A3B8',
          blue:      '#0284C7',
          'blue-light': '#E0F2FE',
          cyan:      '#0891B2',
          green:     '#059669',
          'green-light': '#D1FAE5',
          amber:     '#D97706',
          'amber-light': '#FEF3C7',
          red:       '#DC2626',
          'red-light': '#FEE2E2',
          purple:    '#7C3AED',
          'purple-light': '#EDE9FE',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      boxShadow: {
        'card': '0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.06)',
        'card-hover': '0 4px 6px -1px rgb(0 0 0 / 0.07), 0 2px 4px -2px rgb(0 0 0 / 0.05)',
        'panel': '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        'popup': '0 10px 25px -5px rgb(0 0 0 / 0.12), 0 8px 10px -6px rgb(0 0 0 / 0.06)',
      },
    },
  },
  plugins: [],
};
