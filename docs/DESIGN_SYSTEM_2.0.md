# Accountinox Design System 2.0 (Tailwind CSS)

## 1. Design Philosophy
Modern, clean, trustworthy, and Persian-optimized.
- **Visual Style**: Flat surfaces, subtle shadows, rounded corners (Apple/Google style), high contrast text.
- **Motion**: Fast, fluid micro-interactions (200ms-300ms).
- **Mobile-First**: Touch targets >= 44px, readable text on small screens.

---

## 2. Design Tokens (Tailwind Configuration)

### Color Palette
We refine the existing Teal/Blue brands to be more vibrant and accessible.

```javascript
// tailwind.config.js updates
colors: {
  // Primary (Brand Identity - Trust/Tech/Security) - slightly more saturated than before
  primary: {
    50: '#f0fdfa',
    100: '#ccfbf1',
    200: '#99f6e4',
    300: '#5eead4',
    400: '#2dd4bf',
    500: '#14b8a6', // Main Brand Color
    600: '#0d9488', // Hover state
    700: '#0f766e',
    800: '#115e59',
    900: '#134e4a',
    950: '#042f2e',
  },
  // Secondary (Action/Info) - Deep Corporate Blue
  secondary: {
    50: '#eff6ff',
    100: '#dbeafe',
    200: '#bfdbfe',
    300: '#93c5fd',
    400: '#60a5fa',
    500: '#3b82f6', // Secondary Action
    600: '#2563eb',
    700: '#1d4ed8',
    800: '#1e40af', // Deep footer background
    900: '#1e3a8a',
    950: '#172554',
  },
  // Semantic Colors (Success/Warning/Error)
  success: { 500: '#22c55e', 50: '#f0fdf4' },
  warning: { 500: '#eab308', 50: '#fefce8' },
  error:   { 500: '#ef4444', 50: '#fef2f2' },
  // Neutrals (Text/Backgrounds) - Slate preferred for tech vibe
  slate: {
    50:  '#f8fafc', // Page Background
    100: '#f1f5f9', // Card Background / Hover
    200: '#e2e8f0', // Borders / Dividers
    300: '#cbd5e1', // Disabled inputs
    400: '#94a3b8', // Icons / Placeholder text
    500: '#64748b', // Secondary Text
    600: '#475569', // Body Text
    700: '#334155', // Headings (Light mode)
    800: '#1e293b', // Headings / Dark mode bg
    900: '#0f172a', // Heavy contrast actions
  }
}
```

### Typography (Vazirmatn)
```javascript
fontFamily: {
  sans: ['Vazirmatn', 'ui-sans-serif', 'system-ui', 'sans-serif'],
},
fontSize: {
  xs: ['0.75rem', { lineHeight: '1rem' }],
  sm: ['0.875rem', { lineHeight: '1.5rem' }],     // Body small
  base: ['1rem', { lineHeight: '1.75rem' }],      // Body default
  lg: ['1.125rem', { lineHeight: '1.75rem' }],    // Large text
  xl: ['1.25rem', { lineHeight: '1.75rem' }],     // H4
  '2xl': ['1.5rem', { lineHeight: '2rem' }],      // H3
  '3xl': ['1.875rem', { lineHeight: '2.25rem' }], // H2
  '4xl': ['2.25rem', { lineHeight: '2.5rem' }],   // H1
}
```

### Shadows & Radius
```javascript
boxShadow: {
  card: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
  'card-hover': '0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -2px rgba(0, 0, 0, 0.04)',
  floating: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
},
borderRadius: {
  lg: '0.75rem', // 12px for cards/inputs
  xl: '1rem',    // 16px for large surfaces
  '2xl': '1.5rem', // 24px for modals
}
```

---

## 3. Component Guidelines (Class Recipes)

### Buttons
**Role**: Primary Call-to-Action
```html
<button class="
  inline-flex items-center justify-center 
  rounded-lg px-6 py-2.5 text-sm font-semibold text-white 
  bg-primary-600 hover:bg-primary-700 active:bg-primary-800
  transition-all duration-200 shadow-md shadow-primary-500/20 
  focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2
">
  خرید محصول
</button>
```

**Role**: Secondary / Outline
```html
<button class="
  inline-flex items-center justify-center 
  rounded-lg px-6 py-2.5 text-sm font-semibold text-slate-700 
  bg-white border border-slate-200 hover:bg-slate-50 hover:border-slate-300 hover:text-slate-900
  transition-all duration-200 
  focus:outline-none focus:ring-2 focus:ring-slate-200
">
  جزئیات بیشتر
</button>
```

**Role**: Ghost / Text Only
```html
<button class="
  inline-flex items-center justify-center 
  rounded-lg px-4 py-2 text-sm font-medium text-slate-600 
  hover:bg-slate-100 hover:text-slate-900 
  transition-colors
">
  لغو
</button>
```

### Cards (Product / Content)
```html
<div class="
  group relative overflow-hidden rounded-xl bg-white 
  border border-slate-100 shadow-card 
  hover:shadow-card-hover hover:-translate-y-1 
  transition-all duration-300 ease-out
">
  <!-- Image/Header -->
  <div class="aspect-video bg-slate-100 relative">
     <img src="..." class="w-full h-full object-cover">
  </div>
  <!-- Body -->
  <div class="p-5">
    <h3 class="font-bold text-slate-900 text-lg mb-2">عنوان محصول</h3>
    <p class="text-sm text-slate-500 line-clamp-2">توضیحات کوتاه محصول...</p>
  </div>
</div>
```

### Forms (Inputs)
```html
<div>
  <label class="block text-sm font-medium text-slate-700 mb-1.5">ایمیل شما</label>
  <input type="email" class="
    w-full rounded-lg border-slate-200 bg-slate-50 
    px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400
    focus:bg-white focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 
    transition-all duration-200
  " placeholder="name@example.com">
</div>
```

---

## 4. Animation & Micro-interactions
Add these keyframes to your custom CSS or tailwind config.

**Fade Up (Entry Animation)**
```css
@keyframes fade-up {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-fade-up { animation: fade-up 0.4s ease-out forwards; }
```

**Scale In (Modals/Popups)**
```css
@keyframes scale-in {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}
.animate-scale-in { animation: scale-in 0.2s ease-out forwards; }
```

---

## 5. Support Chat Widget Redesign
A modern, Telegram/WhatsApp web inspired layout. Fully responsive.

### Desktop/Tablet View
- **Sidebar**: List of past chats or quick actions (width: 80px or 320px).
- **Main Area**: Chat history + Input area.

### Chat Container Structure
```html
<!-- Main Chat Wrapper -->
<div class="flex flex-col h-[calc(100vh-140px)] md:h-[600px] w-full max-w-5xl mx-auto bg-white rounded-2xl shadow-xl overflow-hidden border border-slate-200">
  
  <!-- Header -->
  <header class="bg-slate-50 border-b border-slate-200 px-6 py-4 flex items-center justify-between">
    <div class="flex items-center gap-4">
      <div class="relative">
        <div class="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center text-primary-600">
          <!-- Icon -->
          <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" /></svg>
        </div>
        <span class="absolute bottom-0 right-0 w-3 h-3 bg-green-500 border-2 border-white rounded-full"></span>
      </div>
      <div>
        <h2 class="font-bold text-slate-800">پشتیبانی آنلاین</h2>
        <p class="text-xs text-slate-500">پاسخگویی معمولاً در کمتر از ۵ دقیقه</p>
      </div>
    </div>
    <button class="btn-ghost p-2 rounded-full text-slate-400 hover:bg-slate-200 hover:text-slate-600 transition-colors">
      <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
    </button>
  </header>

  <!-- Messages Area -->
  <div class="flex-1 bg-[#efeae2] p-4 overflow-y-auto space-y-4" style="background-image: url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png'); opacity: 0.95;">
    
    <!-- Operator Message -->
    <div class="flex justify-start">
      <div class="max-w-[80%] bg-white rounded-2xl rounded-tr-none shadow-sm px-4 py-2.5 text-sm text-slate-800 relative group">
        <p>سلام! چطور میتونم کمکتون کنم؟ 👋</p>
        <div class="text-[10px] text-slate-400 text-left mt-1">14:20</div>
      </div>
    </div>

    <!-- User Message -->
    <div class="flex justify-end">
      <div class="max-w-[80%] bg-primary-500 rounded-2xl rounded-tl-none shadow-sm px-4 py-2.5 text-sm text-white">
        <p>سلام، برای خرید اکانت سوال داشتم.</p>
        <div class="text-[10px] text-white/70 text-right mt-1 flex items-center justify-end gap-1">
          <span>14:22</span>
          <!-- Double tick icon -->
          <svg class="w-3 h-3" viewBox="0 0 16 15" width="16" height="15"><path fill="currentColor" d="M15.01 3.316l-.478-.372a.365.365 0 0 0-.51.063L8.666 9.879a.32.32 0 0 1-.484.033l-.358-.325a.319.319 0 0 0-.484.032l-.378.483a.418.418 0 0 0 .036.541l1.32 1.266c.143.14.361.125.484-.033l6.272-8.048a.366.366 0 0 0-.064-.512zm-4.1 0l-.478-.372a.365.365 0 0 0-.51.063L4.566 9.879a.32.32 0 0 1-.484.033L1.891 7.769a.366.366 0 0 0-.515.006l-.423.433a.364.364 0 0 0 .006.514l3.258 3.185c.143.14.361.125.484-.033l6.272-8.048a.366.366 0 0 0-.064-.512z"/></svg>
        </div>
      </div>
    </div>

  </div>

  <!-- Input Area -->
  <footer class="bg-white border-t border-slate-200 p-3 sm:p-4">
    <form class="flex items-end gap-2">
      <button type="button" class="p-2 text-slate-400 hover:text-slate-600 transition-colors">
        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" /></svg>
      </button>
      <div class="flex-grow bg-slate-50 rounded-xl flex items-center border border-transparent focus-within:border-primary-300 focus-within:ring-2 focus-within:ring-primary-100 transition-all">
        <textarea rows="1" class="w-full bg-transparent border-0 focus:ring-0 px-4 py-3 text-sm text-slate-800 placeholder:text-slate-400 max-h-32 resize-none" placeholder="اینجا بنویسید..."></textarea>
      </div>
      <button type="submit" class="p-3 bg-primary-500 text-white rounded-xl hover:bg-primary-600 active:scale-95 transition-all shadow-md shadow-primary-500/20">
        <svg class="w-5 h-5 rtl:rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" /></svg>
      </button>
    </form>
  </footer>

</div>
```
