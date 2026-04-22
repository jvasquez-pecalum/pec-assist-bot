# Paramount AI Portal - Design System Documentation

A comprehensive technical guide to the Paramount AI Portal's design system for LLM vibecoders. This document enables pixel-perfect replication of all styles, colors, layouts, and interactive patterns.

---

## 1. COLOR PALETTE

### Primary Colors (Paramount Extrusions Brand)

| Name | Hex | CSS Variable | Usage |
|------|-----|--------------|-------|
| **PE Yellow** | `#FFCC00` | `bg-pe-yellow`, `text-pe-yellow` | CTA buttons, active states, accents |
| **PE Black** | `#111111` | `bg-pe-black`, `text-pe-black` | Text, borders, dark surfaces, sidebar |
| **PE Gray** | `#F0F0F0` | `bg-pe-gray`, `text-pe-gray` | Backgrounds, secondary surfaces, inputs |
| **PE Dark Gray** | `#222222` | `bg-pe-darkgray`, `text-pe-darkgray` | Text, hover states, secondary text |

### Extended Color Scales (Legacy Paramount)

**Paramount Blue Scale** (now mapped to grayscale):
```
50: #F0F0F0    | 100: #E0E0E0   | 200: #C0C0C0   | 300: #A0A0A0
400: #808080   | 500: #606060   | 600: #404040   | 700: #222222
800: #111111   | 900: #000000   | 950: #000000
```

**Paramount Silver Scale** (light grays):
```
50: #FFFFFF    | 100: #F8F8F8   | 200: #F0F0F0   | 300: #E0E0E0
400: #D0D0D0   | 500: #C0C0C0   | 600: #A0A0A0   | 700: #808080
800: #606060   | 900: #404040
```

**Paramount Orange Scale** (variants of yellow):
```
50: #FFF8E0    | 100: #FFEFC0   | 200: #FFE090   | 300: #FFD060
400: #FFC030   | 500: #FFCC00   | 600: #E0B000   | 700: #C09000
800: #A07000   | 900: #805000
```

### Semantic Colors (Status/Feedback)
- **Success**: `#16a34a` (green-600)
- **Warning**: `#FFCC00` (pe-yellow)
- **Error**: `#dc2626` (red-600)
- **Info**: `#2563eb` (blue-500)

---

## 2. TYPOGRAPHY SYSTEM

### Font Families

| Type | Font Stack | CSS |
|------|-----------|-----|
| **Body/UI** | Inter, system-ui, -apple-system, sans-serif | `font-sans` |
| **Display** | Inter, sans-serif | `font-display` |
| **Monospace** | JetBrains Mono, monospace | `font-mono` |

**Font Weights Used:**
- `font-medium` (500) - Secondary text
- `font-bold` (600) - Descriptive text, secondary headings
- `font-black` (900) - Primary headings, buttons, labels

### Typography Scale & Classes

| Element | Size | Weight | Case | Tracking | Tailwind Class |
|---------|------|--------|------|----------|-----------------|
| **Page Title** | 48px (4xl) / 60px (5xl) | black (900) | UPPERCASE | tight | `.page-title` |
| **Page Subtitle** | 18px (lg) | semibold (600) | - | - | `.page-subtitle` |
| **Section Title** | 24px (2xl) | black (900) | UPPERCASE | tight | `.section-title` |
| **Card Heading** | 18px (lg) | black (900) | UPPERCASE | tight | Applied inline in `Card` component |
| **Card Description** | 14px (sm) | bold (600) | UPPERCASE | wider | Applied inline in `Card` component |
| **Button Text** | 14px (sm) | black (900) | UPPERCASE | wider | `.btn-primary`, `.btn-secondary`, `.btn-dark` |
| **Badge** | 12px (xs) | black (900) | UPPERCASE | widest | `.badge`, `.badge-yellow`, etc. |
| **Body Text** | 14px (sm) / 16px (base) | medium (500) / bold (600) | - | - | Default, or applied per context |
| **Small Text** | 12px (xs) | bold (600) | UPPERCASE | widest | Applied inline for secondary labels |

### Letter Spacing Scale

| Class | Value | Usage |
|-------|-------|-------|
| `tracking-tighter` | -0.05em | Tight headings |
| `tracking-tight` | -0.025em | Section titles, page titles |
| `tracking-wide` | 0.025em | Body text |
| `tracking-wider` | 0.05em | Buttons, labels |
| `tracking-widest` | 0.1em | Badges, small caps |

---

## 3. BORDER & SHADOW SYSTEM

### Border Styles

| Width | Thickness | Tailwind Class | Usage |
|-------|-----------|-----------------|-------|
| Thin | 1px | `border` | (rarely used) |
| Medium | 2px | `border-2` | Badge borders, scrollbar |
| Thick | 3px | `border-[3px]` | Card borders, input borders, component dividers |
| Extra Thick | 4px | `border-4` | Header/sidebar dividers, major section breaks |

**Border Colors:**
- Primary: `border-pe-black` (3px borders on all cards, inputs)
- Secondary: `border-pe-yellow` (accents, special states)
- Tertiary: `border-pe-gray` (table rows, light dividers)

### Shadow System (Industrial "Concrete Block" Style)

| Name | Definition | Usage |
|------|-----------|-------|
| `shadow-solid` | `8px 8px 0px 0px #111111` | Large cards, major components |
| `shadow-solid-sm` | `4px 4px 0px 0px #111111` | Smaller cards, stat cards |
| `shadow-solid-yellow` | `8px 8px 0px 0px #FFCC00` | Dark cards on yellow accent |
| `shadow-solid-white` | `8px 8px 0px 0px #FFFFFF` | (alternative accent shadow) |

**Shadow Behavior:**
- Shadows are **solid, hard-edged offsets** (not blur-based), creating an industrial "concrete block" aesthetic
- Applied via `shadow-solid` or `shadow-solid-sm` Tailwind classes
- On hover/active states, elements translate to "collapse" the shadow

---

## 4. SPACING & LAYOUT

### Spacing Scale

Tailwind's default spacing scale is used (4px base unit):
```
0px, 4px (1), 8px (2), 12px (3), 16px (4), 20px (5), 24px (6),
28px (7), 32px (8), 36px (9), 40px (10), etc.
```

### Common Spacing Values

| Component | Padding | Margin | Notes |
|-----------|---------|--------|-------|
| **Card** | `p-6` (24px) | - | Content area inside cards |
| **Card Header/Footer** | `px-6 py-4` (24px / 16px) | - | Title/description/action area |
| **Button** | `px-5 py-3` (20px / 12px) | - | Horizontal / vertical padding |
| **Input Field** | `px-4 py-3` (16px / 12px) | - | Form inputs |
| **Page Content** | `p-6` (mobile) `p-8` (desktop) | - | Main page container |
| **Sidebar** | `px-4 py-6` | - | Navigation section spacing |
| **Gap (Flex)** | `gap-3` to `gap-6` | - | Between flex items |

### Layout Grid & Containers

- **Sidebar Width**: `w-64` (256px) — Fixed left sidebar on desktop (hidden on mobile)
- **Main Content**: `flex-1` — Flexible container that grows to fill remaining space
- **Header Height**: `h-20` (80px) — Fixed height header with 4px border
- **Responsive Breakpoints**:
  - `md:` (768px) — Tablets
  - `lg:` (1024px) — Desktops (sidebar appears, layout shifts)

---

## 5. COMPONENT SYSTEM

### Card Component

**Variants:**
```
variant: 'white' | 'yellow' | 'gray' | 'dark'
```

**Examples:**

```tsx
// White Card (default)
<Card title="Title" description="Subtitle" icon={IconComponent} variant="white">
  Content here
</Card>
// Background: #FFFFFF, Border: 3px #111111, Shadow: 8px 8px #111111

// Yellow Card
<Card title="Title" variant="yellow">
  Content here
</Card>
// Background: #FFCC00, Border: 3px #111111, Shadow: 8px 8px #111111

// Gray Card
<Card title="Title" variant="gray">
  Content here
</Card>
// Background: #F0F0F0, Border: 3px #111111, Shadow: 8px 8px #111111

// Dark Card
<Card title="Title" variant="dark">
  Content here
</Card>
// Background: #111111, Text: white, Border: 3px #111111, Shadow: 8px 8px #111111
```

**Card Icon Area:**
- Icon container: 3px border, `bg-pe-yellow`, 20px x 20px icon
- Position: Top-left, inside `px-6 py-4` header area

**Card Sections:**
- Header: `px-6 py-4`, `border-b-[3px] border-pe-black`
- Content: `p-6`
- Footer: `px-6 py-4`, `border-t-[3px] border-pe-black`, `bg-pe-gray`

### StatCard Component

**Variants:**
```
variant: 'white' | 'yellow' | 'black'
```

**Layout:**
- Icon on right side, `w-6 h-6`
- Title (xs, bold, uppercase) + Value (3xl, black) + Change % on left
- Flex between layout
- Padding: `p-6`
- Shadow: `shadow-solid-sm` (4px 4px)

**Color Variants:**
```
WHITE:  bg-white, text-pe-black, icon bg-pe-yellow with black border
YELLOW: bg-pe-yellow, text-pe-black, icon bg-pe-black with black border
BLACK:  bg-pe-black, text-white, icon bg-pe-yellow with yellow border
```

### ToolCard Component

**Variants:**
```
variant: 'yellow' | 'gray' | 'black' | 'white'
```

**Layout:**
- Icon block: `w-14 h-14`, 3px border, centered icon
- Title (lg, black, uppercase)
- Description (sm, pe-darkgray)
- "GET STARTED" CTA with arrow that translates on hover
- Link wrapper for navigation

**Hover Behavior:**
```
- Translate: -translate-y-1 -translate-x-1 (move up-left)
- Shadow upgrade: shadow-solid-sm → shadow-solid (8px offset)
- Color shift depends on variant:
  white → hover:bg-pe-yellow
  yellow → hover:bg-white
  gray → hover:bg-pe-yellow
  black → hover:bg-pe-darkgray
```

### Badge Component

**Variants:**
```
'default' | 'success' | 'warning' | 'error' | 'info' | 'yellow' | 'black' | 'white'
```

**Base Style:**
- Padding: `px-3 py-1`
- Font: 12px, black (900), uppercase, tracking-widest
- Border: 2px border
- Display: `inline-flex` items-center

**Color Mappings:**
| Variant | Background | Text | Border |
|---------|-----------|------|--------|
| default | pe-gray (#F0F0F0) | pe-black | pe-black |
| success | green-500 (#16a34a) | white | pe-black |
| warning | pe-yellow (#FFCC00) | pe-black | pe-black |
| error | red-500 (#dc2626) | white | pe-black |
| info | blue-500 (#2563eb) | white | pe-black |
| yellow | pe-yellow (#FFCC00) | pe-black | pe-black |
| black | pe-black (#111111) | white | pe-black |
| white | white (#FFFFFF) | pe-black | pe-black |

### Button System

**Classes & Styles:**

```css
/* Primary Button - Yellow */
.btn-primary {
  background: pe-yellow (#FFCC00)
  text: pe-black
  border: 3px solid pe-black
  shadow: shadow-solid-sm (4px 4px #111111)
  padding: px-5 py-3
  font: black, uppercase, tracking-wider
  hover: bg-white
  active: translate(4px, 4px), shadow collapse to 0
  focus: ring-2 ring-pe-yellow ring-offset-2
}

/* Secondary Button - White */
.btn-secondary {
  background: white
  text: pe-black
  border: 3px solid pe-black
  shadow: shadow-solid-sm
  padding: px-5 py-3
  font: black, uppercase, tracking-wider
  hover: bg-pe-yellow
  active: translate(4px, 4px), shadow collapse
  focus: ring-2 ring-pe-black ring-offset-2
}

/* Dark Button - Black */
.btn-dark {
  background: pe-black
  text: white
  border: 3px solid pe-black
  shadow: shadow-solid-sm
  padding: px-5 py-3
  font: black, uppercase, tracking-wider
  hover: bg-pe-darkgray
  active: translate(4px, 4px), shadow collapse
  focus: ring-2 ring-pe-black ring-offset-2
}
```

### Input Fields

**Standard Input:**
```css
.input-field {
  background: white
  border: 3px solid pe-black
  padding: px-4 py-3
  font: medium (500), pe-black text
  placeholder: pe-darkgray
  focus: outline-none, ring-2 ring-pe-yellow, border-pe-black
}
```

**Dark Input (for dark backgrounds):**
```css
.input-field-dark {
  background: pe-black
  border: 3px solid gray-600
  padding: px-4 py-3
  font: medium (500), white text
  placeholder: gray-500
  focus: ring-2 ring-pe-yellow, border-pe-yellow
  autofill: -webkit-box-shadow 1000px inset #111111, text-pe-yellow
}
```

**Error State:**
```css
.input-field-error {
  border: red-600
  focus: ring-red-500
}
```

---

## 6. LAYOUT SYSTEM

### AppLayout Structure

```
┌─────────────────────────────────────────┐
│          Header (fixed, h-20)           │
│ Mobile Menu | Search | Notifications   │
└─────────────────────────────────────────┘
┌───────────────────────────────────────────────┐
│ SIDEBAR    │                                 │
│ (w-64)     │      Main Content Area         │
│ (fixed)    │      (flex-1, p-6 lg:p-8)      │
│            │                                 │
│            │      <Outlet /> (page content) │
│            │                                 │
└───────────────────────────────────────────────┘
```

**Sidebar** (Desktop only, `hidden lg:flex`):
- Fixed width: `w-64` (256px)
- Fixed position: `lg:fixed lg:inset-y-0 lg:left-0`
- Background: `bg-pe-black`
- Text: `text-white`
- Border-right: 4px border-pe-yellow (after logo)
- Sections: Logo, Navigation, User Profile

**Header**:
- Full width, fixed to top
- Height: `h-20` (80px)
- Background: `bg-white`
- Border-bottom: 4px solid pe-black
- Sticky: `sticky top-0 z-30`

**Main Content**:
- Left margin on desktop: `lg:ml-64` (matches sidebar width)
- Padding: `p-6` (mobile), `p-8` (desktop)
- Flex-grow to fill available space

---

## 7. INTERACTIVE STATES & ANIMATIONS

### Hover States

**Buttons & Cards:**
```
Translate: -translate-y-1 -translate-x-1  (move up-left 4px)
Shadow: Upgrade to larger shadow (4px → 8px or maintain)
Color: Shift to variant-specific hover color
```

**Navigation Links:**
```
Text color: Shift to pe-yellow on hover
Background: Shift to pe-darkgray on hover
Duration: 150ms ease-in-out
```

### Active/Focus States

**Buttons:**
```
Active (pressed): translate(4px, 4px) — collapses shadow visually
Focus: ring-2 ring-{color} ring-offset-2
```

**Navigation (Active Route):**
```
Sidebar Nav:
  - Background: bg-pe-yellow
  - Text: text-pe-black
  - Shadow: shadow-solid-sm
  - Transform: translate-x-1 translate-y-1
```

**Inputs:**
```
Focus:
  - outline: none
  - ring: ring-2 ring-pe-yellow (standard), ring-red-500 (error)
  - border: maintained
```

### Animations

**Fade In:**
```css
animation: fadeIn 0.3s ease-in-out;
keyframes: 0% { opacity: 0 } → 100% { opacity: 1 }
```

**Slide Up:**
```css
animation: slideUp 0.3s ease-out;
keyframes: 0% { transform: translateY(10px), opacity: 0 }
           → 100% { transform: translateY(0), opacity: 1 }
```

**Loading Spinner:**
- Icon: `animate-spin` class
- Color: `text-pe-yellow`
- Border: `border-[3px] border-pe-black`

---

## 8. SPECIAL COMPONENTS

### Navigation Link (Sidebar)

**Inactive:**
```
text-gray-300 hover:text-pe-yellow hover:bg-pe-darkgray
transition-all duration-150
flex items-center gap-3 px-4 py-3 text-sm font-bold uppercase tracking-wider
```

**Active:**
```
bg-pe-yellow text-pe-black shadow-solid-sm
transform translate-x-1 translate-y-1
flex items-center gap-3 px-4 py-3 text-sm font-bold uppercase tracking-wider
```

### Chat Messages

**User Message:**
```
bg-pe-yellow text-pe-black border-[3px] border-pe-black
shadow-solid-sm px-4 py-3 max-w-[80%] ml-auto
```

**Assistant Message:**
```
bg-pe-gray text-pe-black border-[3px] border-pe-black
px-4 py-3 max-w-[80%]
```

### Tables

**Header Row:**
```
background: pe-gray
border-bottom: 3px solid pe-black
padding: px-4 py-3
font: sm, black (900), uppercase, tracking-wider
text: pe-black
```

**Table Data Cell:**
```
border-bottom: 2px solid pe-gray
padding: px-4 py-3
font: sm, pe-black
```

**Hover Row:**
```
background: pe-gray (highlight entire row on hover)
```

### Loading & Empty States

**Loading State:**
- Spinner: `Loader2` icon, `animate-spin`, `text-pe-yellow`, `border-[3px] border-pe-black`
- Message: `text-pe-black`, bold, uppercase, tracking-wider, `text-sm`
- Container: `flex flex-col items-center justify-center p-8`

**Empty State:**
- Icon: `text-pe-darkgray`
- Title: `text-lg`, black (900), uppercase, tracking-tight, `text-pe-black`
- Description: `text-sm`, bold, `text-pe-darkgray`
- Container: centered flex, `p-12`, `text-center`

**Error State:**
- Error box: `w-12 h-12`, `border-[3px] border-red-600`, `bg-red-100`
- Icon: `w-6 h-6`, `text-red-600`
- Title: same as empty state
- Description: same as empty state
- Retry button: `btn-secondary`

---

## 9. SCROLLBAR STYLING

**Custom Scrollbar (WebKit browsers):**
```css
::-webkit-scrollbar {
  width: 12px;
}

::-webkit-scrollbar-track {
  background: pe-gray (#F0F0F0)
  border-left: 2px solid pe-black (#111111)
}

::-webkit-scrollbar-thumb {
  background: pe-yellow (#FFCC00)
  border: 2px solid pe-black
}

::-webkit-scrollbar-thumb:hover {
  background: pe-black (#111111)
}
```

---

## 10. RESPONSIVE DESIGN

### Breakpoints

| Breakpoint | Width | Tailwind Prefix | Usage |
|-----------|-------|-----------------|-------|
| Mobile | < 768px | (none) | Default styles |
| Tablet | 768px+ | `md:` | Medium screens |
| Desktop | 1024px+ | `lg:` | Large screens, sidebar visible |

### Key Responsive Behaviors

**Navigation:**
- Mobile: `hidden` sidebar, mobile menu in header (`lg:hidden`)
- Desktop: `hidden lg:flex` sidebar, full navigation

**Header:**
- Mobile: Menu button, compact layout
- Desktop: Search visible, full welcome message

**Layout:**
- Mobile: Full-width content, `ml-0`, `p-6`
- Desktop: Sidebar offset, `lg:ml-64`, `lg:p-8`

**Typography:**
- Mobile: `text-4xl` page titles
- Desktop: `md:text-5xl` page titles

---

## 11. PIXEL DENSITY & PRECISION

### Border Radius
- **None** used in the design (all boxes are sharp/square)
- Corners are hard-edged, no rounding

### Line Height
- Default Tailwind line heights apply
- No custom line-height overrides in the design

### Letter Spacing
- Custom scales applied as documented in Section 2
- Uppercase text consistently uses `tracking-wide`, `tracking-wider`, or `tracking-widest`

### Pseudo-elements
- Used for badge dots/indicators
- Used for input focus rings
- No decorative borders or background patterns beyond solid colors

---

## 12. IMPLEMENTATION RULES FOR VIBECODERS

### Color Substitution Rules
When recreating the design:
1. All `#111111` (pe-black) must map to the brand's darkest color
2. All `#FFCC00` (pe-yellow) must map to the brand's accent color
3. All `#F0F0F0` (pe-gray) must map to the brand's light background
4. All `#222222` (pe-darkgray) must map to a slightly darker gray

### Typography Rules
1. **Inter font** is non-negotiable for body/display text (or direct sans-serif equivalent)
2. **JetBrains Mono** for code/monospace (or monospace equivalent)
3. **Font weights:** Always use 600 (bold) or 900 (black) — never light or thin
4. **Text transform:** Buttons, labels, badges, headings are UPPERCASE
5. **Tracking:** Maintain the specific letter-spacing values per element

### Border Rules
1. All major components use **3px solid borders**
2. Header/sidebar dividers use **4px solid borders**
3. All borders are **pe-black** unless explicitly yellow for accents
4. Shadows are **hard-edged, solid offsets** (8px 8px 0px), not blurred

### Button Rules
1. **Always include shadow-solid-sm** (4px 4px offset)
2. **On active/press:** Translate(4px, 4px) to collapse shadow
3. **On focus:** Include focus ring (`ring-2` + `ring-offset-2`)
4. **Padding:** 20px horizontal, 12px vertical minimum

### Card Rules
1. **Minimum 3px border** with pe-black
2. **Shadow-solid or shadow-solid-sm** required
3. **Header/footer:** Always use 3px border-bottom/top if present
4. **Padding consistency:** 24px standard for cards, 16px for headers/footers

### Spacing Rules
1. **Gap between flex items:** Minimum `gap-3` (12px)
2. **Card padding:** `p-6` (24px) standard
3. **Page padding:** `p-6` mobile, `p-8` desktop
4. **No margin collapse** — use padding instead

### Animation Rules
1. **Duration:** 150ms for quick interactions (hover, press)
2. **Duration:** 300ms for content animations (fade, slide)
3. **Easing:** `ease-in-out` for smooth, `ease-out` for entrance
4. **Translate:** -1 unit (4px) for hover elevation

---

## 13. DARK MODE (Not Implemented)

The current design does **not** support dark mode. If implementing dark mode in the future:
- Sidebar already uses `bg-pe-black` (dark base)
- Input fields have `.input-field-dark` styles ready
- Consider inverting the color palette rather than adding true dark mode

---

## 14. QUICK REFERENCE: Component CSS Classes

```
// Buttons
.btn-primary        // Yellow CTA
.btn-secondary      // White secondary
.btn-dark           // Black dark

// Cards
.card               // White card
.card-yellow        // Yellow card
.card-gray          // Gray card
.card-dark          // Black card
.card-hover         // Add hover translation

// Input
.input-field        // Standard text input
.input-field-dark   // Dark background input
.input-field-error  // Error state

// Badges
.badge              // Base badge
.badge-yellow       // Yellow badge
.badge-black        // Black badge
.badge-gray         // Gray badge
.badge-white        // White badge
.badge-success      // Green success
.badge-error        // Red error
.badge-warning      // Yellow warning

// Typography
.page-header        // Page title container
.page-title         // Large page heading
.page-subtitle      // Subtitle below title
.section-title      // Section heading

// Navigation
.nav-link           // Sidebar nav item
.nav-link-active    // Active nav state

// States
.table-industrial   // Industrial table style
.stat-card          // Stat display card
.stat-card-dark     // Dark stat card
.tool-card          // Tool/action card
.chat-message-user  // User chat bubble
.chat-message-assistant // Assistant chat bubble

// Utilities
.text-gradient      // Gradient text (yellow)
.border-gradient    // Gradient border
.active-pilot-tab   // Active tab indicator
```

---

## 15. FILE REFERENCE GUIDE

- **Colors**: `tailwind.config.js` (lines 9-25)
- **Shadows**: `tailwind.config.js` (lines 31-40)
- **Typography**: `tailwind.config.js` (lines 26-30)
- **Component Classes**: `src/index.css` (all custom layers)
- **Card Component**: `src/components/common/Card.tsx`
- **Sidebar**: `src/components/layout/Sidebar.tsx`
- **Header**: `src/components/layout/Header.tsx`
- **Badge**: `src/components/common/Badge.tsx`
- **Loading States**: `src/components/common/LoadingState.tsx`

---

## Summary

The Paramount AI Portal uses a **bold, industrial design system** with:
- ✅ Hard-edged, solid shadows (no blur)
- ✅ Bright yellow accents on dark/light backgrounds
- ✅ Heavy, uppercase typography (Inter 900/600)
- ✅ Thick borders (3px standard, 4px for dividers)
- ✅ Minimal color palette (black, yellow, grays)
- ✅ Spatial feedback via translate transforms
- ✅ Component-driven styling via Tailwind CSS

This creates a **recognizable, distinctive brand presence** that's easy to replicate when the color/font variables are substituted.

