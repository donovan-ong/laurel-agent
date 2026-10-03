import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// One self-contained IIFE, so a host page (or the extension) needs a single script and nothing else. React
// is bundled in; the CSS is imported as a string (?inline) and injected into a Shadow DOM, not the page.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    lib: { entry: 'src/index.jsx', name: 'LaurelWidget', formats: ['iife'], fileName: () => 'laurel-widget.js' },
    cssCodeSplit: false,
    emptyOutDir: true,
  },
})
