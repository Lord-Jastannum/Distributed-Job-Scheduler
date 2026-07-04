/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#0B0E14',
        panel: '#131720',
        panelhover: '#1B212D',
        border: '#232A38',
        ink: '#E6E9EF',
        muted: '#8B93A7',
        accent: '#5B8DEF',
        queued: '#F5A623',
        running: '#5B8DEF',
        completed: '#3DD68C',
        failed: '#F0506E',
        deadletter: '#B24BF3',
        scheduled: '#7C89A8',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
