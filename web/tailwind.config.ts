import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: { colors: { ink: '#17171c', paper: '#f8f7f4', surface: '#fbfaf8', line: '#dad8d3' } } },
  plugins: [],
} satisfies Config
