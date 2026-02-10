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
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(.98)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'subtle-pop': {
          '0%': { transform: 'scale(.98)', opacity: '0' },
          '60%': { transform: 'scale(1.02)', opacity: '1' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
      },
      animation: {
        'fade-in': 'fade-in 600ms cubic-bezier(0.2,0,0,1) both',
        'fade-up': 'fade-up 500ms cubic-bezier(0.2,0,0,1) both',
        'scale-in': 'scale-in 160ms cubic-bezier(0.2,0,0,1) both',
        'subtle-pop': 'subtle-pop 280ms cubic-bezier(.2,.8,.2,1) both',
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms')({
      strategy: 'class',
    }),
  ],
}