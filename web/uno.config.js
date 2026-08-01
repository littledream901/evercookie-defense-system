import { defineConfig, presetUno, presetAttributify, presetIcons, transformerDirectives } from 'unocss'

export default defineConfig({
  presets: [
    presetUno(),
    presetAttributify(),
    presetIcons({
      scale: 1.2,
      warn: true,
    }),
  ],
  transformers: [transformerDirectives()],
  shortcuts: [
    ['flex-center', 'flex items-center justify-center'],
    ['flex-col-center', 'flex flex-col items-center justify-center'],
    ['flex-between', 'flex items-center justify-between'],
    ['card-hover', 'transition-shadow hover:shadow-lg'],
  ],
  theme: {
    colors: {
      primary: '#18a058',
      danger: '#d03050',
      warning: '#f0a020',
      info: '#2080f0',
    },
  },
})
