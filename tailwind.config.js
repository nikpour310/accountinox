/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './apps/**/templates/**/*.html',
    './apps/**/forms.py',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Vazirmatn', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif'],
      },
      colors: {
        primary: {
          50: '#f0fcfd',
          100: '#dcfce2', // Adjusted for cyan/teal tint
          200: '#bcf6fd',
          300: '#8bedfa',
          400: '#4edbf5',
          500: '#1abbc8', // BRAND - Base
          600: '#129aa7',
          700: '#117b87',
          800: '#11636d',
          900: '#12525c',
          950: '#07363e',
        },
        secondary: {
          50: '#f0f7ff',
          100: '#e0effe',
          200: '#badfff',
          300: '#7cc3ff',
          400: '#36a1ff',
          500: '#0468bd', // BRAND - Secondary
          600: '#00529e',
          700: '#004280',
          800: '#00386b',
          900: '#062f59',
          950: '#041d3a',
        },
      },
      container: {
        center: true,
        padding: '1rem',
        screens: {
          sm: '640px',
          md: '768px',
          lg: '1024px',
          xl: '1280px',
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms')({
      strategy: 'class',
    }),
  ],
}