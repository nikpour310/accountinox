# Accountinox Design System 2.0 (Tailwind CSS)

## 1. Design Philosophy
**Modern, Clean, Trustworthy.**
- **Visual Style**: "Apple-esque" but tailored for Persian UI. Flat surfaces, high-quality whitespace, subtle deep shadows, and rounded corners (12px - 16px).
- **Core Principle**: Mobile-First. Every component is designed for touch (44px+) first, then expanded for mouse users.
- **Accessibility**: AA standard contrast. No subtle grays for essential text. Focus rings on all interactables.
- **NO Dark Mode**: The system is designed for a unified Light Mode experience only.

---

## 2. Tailwind Design Tokens

### Color Palette (Updated)
We use a refined saturation model. `Primary` is Teal (Trust/Security), `Secondary` is Blue (Business).

```javascript
// tailwind.config.js
colors: {
  // Brand: Trust, Security, Speed
  primary: {
    50: '#f0fdfa', 100: '#ccfbf1', 200: '#99f6e4', 300: '#5eead4',
    400: '#2dd4bf', 500: '#14b8a6', 600: '#0d9488', 700: '#0f766e',
    800: '#115e59', 900: '#134e4a', 950: '#042f2e',
  },
  // Action: Links, Info, Corporate
  secondary: {
    50: '#eff6ff', 100: '#dbeafe', 200: '#bfdbfe', 300: '#93c5fd',
    400: '#60a5fa', 500: '#3b82f6', 600: '#2563eb', 700: '#1d4ed8',
    800: '#1e40af', 900: '#1e3a8a', 950: '#172554',
  },
  // Semantics
  success: { 500: '#22c55e', 50: '#f0fdf4' },
  warning: { 500: '#eab308', 50: '#fefce8' },
  error:   { 500: '#ef4444', 50: '#fef2f2' },
  // Neutrals (Slate)
  slate: {
    50: '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 300: '#cbd5e1',
    400: '#94a3b8', 500: '#64748b', 600: '#475569', 700: '#334155', 
    800: '#1e293b', 900: '#0f172a',
  }
}
```

### Spacing & Layout
- **Container**: `max-w-7xl` centered.
- **Section Spacing**: `py-12` (mobile) / `py-20` (desktop).
- **Element Spacing**: `gap-4` (tight) / `gap-6` (standard) / `gap-8` (loose).

### Typography (Vazirmatn)
- **Base**: `text-slate-600` for body, `text-slate-900` for headings.
- **Scale**:
  - H1: `text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight`
  - H2: `text-2xl sm:text-3xl font-bold`
  - H3: `text-xl sm:text-2xl font-bold`
  - Body: `text-base leading-7`
  - Caption: `text-sm text-slate-500`

### Shadows & Radius
- **Cards**: `rounded-2xl shadow-card hover:shadow-card-hover transition-shadow duration-300`
- **Modals/Popups**: `rounded-3xl shadow-floating`
- **Buttons**: `rounded-xl`

---

## 3. Component Guidelines

### Buttons

**Primary (Call to Action)**
```html
<button class="btn btn-primary">
  خرید محصول
</button>
<!-- Definition -->
.btn-primary {
  @apply inline-flex items-center justify-center rounded-xl bg-primary-600 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-primary-500/30 transition-all hover:bg-primary-500 hover:shadow-primary-500/40 hover:-translate-y-0.5 active:translate-y-0 active:shadow-none focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2;
}
```

**Secondary (Outline)**
```html
<button class="btn btn-secondary">
  اطلاعات بیشتر
</button>
<!-- Definition -->
.btn-secondary {
  @apply inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-6 py-3 text-sm font-bold text-slate-700 transition-all hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-200 focus:ring-offset-2;
}
```

**Ghost (Text Link)**
```html
<button class="btn btn-ghost">
  لغو
</button>
<!-- Definition -->
.btn-ghost {
  @apply inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium text-slate-500 transition-colors hover:text-slate-900 hover:bg-slate-100;
}
```

### Cards

**Product Card**
```html
<div class="group relative overflow-hidden rounded-2xl bg-white border border-slate-100 shadow-card transition-all duration-300 hover:shadow-card-hover hover:-translate-y-1">
  <!-- Badge -->
  <span class="absolute top-3 right-3 z-10 rounded-lg bg-green-500/10 px-2.5 py-1 text-xs font-bold text-green-600 backdrop-blur-sm">موجود</span>
  
  <!-- Image -->
  <div class="aspect-[4/3] bg-slate-100 relative overflow-hidden">
    <img src="..." class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-110">
  </div>
  
  <!-- Content -->
  <div class="p-5">
    <div class="mb-2 text-xs font-semibold text-primary-600">دسته‌بندی</div>
    <h3 class="mb-2 text-lg font-bold text-slate-900 group-hover:text-primary-600 transition-colors">عنوان محصول</h3>
    <div class="flex items-end justify-between">
      <div class="flex flex-col">
        <span class="text-xs text-slate-400 line-through">250,000</span>
        <span class="text-lg font-black text-slate-900">199,000 <span class="text-xs font-normal text-slate-500">تومان</span></span>
      </div>
      <button class="rounded-lg bg-primary-50 p-2 text-primary-600 hover:bg-primary-600 hover:text-white transition-colors">
        <svg class="w-5 h-5">...</svg> <!-- Cart Icon -->
      </button>
    </div>
  </div>
</div>
```

### Forms

**Input Text**
```html
<div>
  <label class="mb-1.5 block text-sm font-semibold text-slate-700">شماره موبایل</label>
  <div class="relative">
    <input type="text" class="peer w-full rounded-xl border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 placeholder-slate-400 transition-all focus:border-primary-500 focus:bg-white focus:ring-4 focus:ring-primary-500/10" placeholder="0912...">
    <!-- Validation Icon -->
    <div class="absolute inset-y-0 left-0 flex items-center pl-4 text-green-500 opacity-0 peer-[&:not(:placeholder-shown):valid]:opacity-100">
      <svg class="w-5 h-5">...</svg>
    </div>
  </div>
  <p class="mt-1.5 text-xs text-slate-500">شماره موبایل برای ورود الزامی است.</p>
</div>
```

---

## 4. Motion & Micro-interactions

Utilize the configured custom animations:

- **Entry**: `.animate-fade-up` or `.animate-fade-in` on page load for main content sections.
- **Modals**: `.animate-scale-in` for the modal panel, `.animate-fade-in` for the backdrop.
- **Buttons**: `active:scale-95` for press feedback.
- **Interactions**: `.animate-subtle-pop` for badges or notification dots appearing.

---

## 5. Support Chat Widget Redesign

The widget is responsive and adapts its layout based on the device.

### A. Mobile (Bottom Sheet)
**Behavior**: Clicking the FAB opens a sheet that slides up from the bottom, covering 90% of the screen.

```html
<!-- Mobile specific container (visible sm and below) -->
<div id="mobile-chat-sheet" class="fixed inset-x-0 bottom-0 z-50 transform transition-transform duration-300 translate-y-full md:hidden">
  
  <!-- Handle bar -->
  <div class="bg-white rounded-t-3xl shadow-[0_-5px_25px_-5px_rgba(0,0,0,0.1)] h-[85vh] flex flex-col border-t border-slate-100">
    <div class="flex justify-center p-3 cursor-pointer" onclick="closeSheet()">
      <div class="w-12 h-1.5 bg-slate-300 rounded-full"></div>
    </div>
    
    <!-- Mobile Header -->
    <div class="px-5 pb-3 border-b border-slate-100 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="relative">
          <img src="/static/img/operator.png" class="w-10 h-10 rounded-full border border-white shadow-sm">
          <span class="absolute bottom-0 right-0 w-2.5 h-2.5 bg-green-500 border-2 border-white rounded-full"></span>
        </div>
        <div>
          <h3 class="font-bold text-slate-900">پشتیبانی آنلاین</h3>
          <p class="text-xs text-slate-500">پاسخگویی سریع</p>
        </div>
      </div>
      <button class="p-2 bg-slate-50 rounded-full text-slate-500" onclick="closeSheet()">×</button>
    </div>

    <!-- Chat Area -->
    <div class="flex-1 overflow-y-auto p-4 bg-slate-50 space-y-3">
      <!-- Messages go here -->
    </div>

    <!-- Input Area Mobile -->
    <div class="p-3 bg-white border-t border-slate-100 pb-safe">
      <form class="flex gap-2">
        <input class="flex-1 rounded-full bg-slate-100 px-5 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" placeholder="پیام...">
        <button class="w-11 h-11 flex items-center justify-center rounded-full bg-primary-600 text-white shadow-lg shadow-primary-500/30">
          <svg class="w-5 h-5 rtl:rotate-180">...</svg> <!-- Send Icon -->
        </button>
      </form>
    </div>
  </div>
</div>
```

### B. Desktop (Floating Widget)
**Behavior**: Fixed to bottom-right (RTL: bottom-left). Animated scale-in on toggle.

```html
<!-- Toggle Button (FAB) -->
<button class="fixed bottom-6 left-6 z-40 flex h-16 w-16 items-center justify-center rounded-full bg-primary-600 text-white shadow-floating transition-transform hover:scale-105 hover:bg-primary-700 focus:outline-none focus:ring-4 focus:ring-primary-500/30 md:left-10 md:bottom-10">
  <svg class="h-8 w-8">...</svg> <!-- Chat Icon -->
</button>

<!-- Desktop Widget Container -->
<div class="fixed bottom-28 left-6 z-50 hidden w-[380px] origin-bottom-left flex-col rounded-3xl bg-white shadow-floating ring-1 ring-slate-900/5 transition-all duration-200 animate-scale-in md:flex md:left-10" style="height: 600px; max-height: calc(100vh - 140px);">
  
  <!-- Header with Gradient -->
  <div class="flex items-center justify-between rounded-t-3xl bg-gradient-to-l from-primary-600 to-primary-800 p-5 text-white">
    <div class="flex items-center gap-3">
        <div class="flex -space-x-3 space-x-reverse">
            <img class="w-8 h-8 rounded-full border-2 border-primary-700" src="...">
            <img class="w-8 h-8 rounded-full border-2 border-primary-700" src="...">
        </div>
        <div class="flex flex-col">
            <span class="font-bold text-sm">تیم پشتیبانی</span>
            <span class="text-[10px] opacity-80">معمولاً در ۵ دقیقه پاسخ میدهیم</span>
        </div>
    </div>
    <button class="text-white/80 hover:text-white">
        <svg class="w-5 h-5">...</svg> <!-- Close/Minimize -->
    </button>
  </div>

  <!-- Messages -->
  <div class="flex-1 overflow-y-auto bg-[#f0f4f8] p-4 space-y-4">
    <!-- Date divider -->
    <div class="flex justify-center"><span class="bg-gray-200 text-gray-500 text-[10px] px-2 py-0.5 rounded-full">امروز</span></div>
    
    <!-- Operator Box -->
    <div class="flex flex-col items-start gap-1 max-w-[85%]">
        <div class="bg-white p-3 rounded-2xl rounded-tr-none text-slate-700 text-sm shadow-sm border border-slate-100">
            سلام! چطور میتونم کمکتون کنم؟ 👋
        </div>
        <span class="text-[10px] text-slate-400 px-1">10:00</span>
    </div>

    <!-- User Box -->
    <div class="flex flex-col items-end gap-1 max-w-[85%] self-end">
        <div class="bg-primary-600 p-3 rounded-2xl rounded-tl-none text-white text-sm shadow-md shadow-primary-500/20">
            سلام، من یه سوال در مورد اکانت‌ها داشتم.
        </div>
        <span class="text-[10px] text-slate-400 px-1">10:02</span>
    </div>
  </div>

  <!-- Footer Input -->
  <div class="p-3 border-t border-slate-100 bg-white rounded-b-3xl">
    <form class="relative">
        <textarea rows="1" class="w-full pl-12 pr-4 py-3 bg-slate-50 border-none rounded-xl text-sm focus:ring-2 focus:ring-primary-100 placeholder-slate-400 resize-none" placeholder="پیام خود را بنویسید..."></textarea>
        <button type="submit" class="absolute left-2 bottom-1.5 p-2 text-primary-600 hover:bg-primary-50 rounded-lg transition-colors">
            <svg class="w-5 h-5 rtl:rotate-180">...</svg> <!-- Send -->
        </button>
    </form>
    <div class="mt-2 text-center">
        <a href="#" class="text-[10px] text-slate-400 hover:text-slate-600">قدرت گرفته از Accountinox</a>
    </div>
  </div>
</div>
```

---

## 6. Accessibility Checklist
- **Color Contrast**: All text on white backgrounds uses `text-slate-600` or darker (4.5:1 ratio).
- **Focus States**: Every custom button/input has `focus:ring` styles.
- **ARIA**:
  - Chat toggles should have `aria-label="Open support chat"`.
  - Status messages should use `role="status"`.
  - Icons should have `aria-hidden="true"`.
- **Tap Targets**: All mobile buttons have `min-height: 44px` padding or sizing.

---

## 7. Deliverables & Footer Credit
The footer of the website must explicitly state:
> **Design & Dev by Ramin Jalili**

This has been implemented in `templates/partials/footer.html`.
