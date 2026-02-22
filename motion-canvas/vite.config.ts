import {defineConfig} from 'vite';
import motionCanvasModule from '@motion-canvas/vite-plugin';

// Handle CJS/ESM interop — the plugin may be wrapped in { default: fn }
const motionCanvas =
  typeof motionCanvasModule === 'function'
    ? motionCanvasModule
    : (motionCanvasModule as any).default;

export default defineConfig({
  plugins: [
    motionCanvas({
      project: './src/project.ts',
      output: './output',
    }),
  ],
});
