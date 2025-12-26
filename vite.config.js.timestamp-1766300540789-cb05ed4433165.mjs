// vite.config.js
import { defineConfig } from "file:///Users/litseliu/Documents/Prototypes/lobechat2/node_modules/vite/dist/node/index.js";
import react from "file:///Users/litseliu/Documents/Prototypes/lobechat2/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5176,
    strictPort: true,
    proxy: {
      "/api": "http://localhost:8787"
    },
    watch: {
      // Avoid spurious restarts when editors/sync tools touch env/config/cache folders.
      ignored: ["**/.env*", "**/vite.config.js", "**/.venv/**", "**/node_modules/.vite/**"]
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvVXNlcnMvbGl0c2VsaXUvRG9jdW1lbnRzL1Byb3RvdHlwZXMvbG9iZWNoYXQyXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCIvVXNlcnMvbGl0c2VsaXUvRG9jdW1lbnRzL1Byb3RvdHlwZXMvbG9iZWNoYXQyL3ZpdGUuY29uZmlnLmpzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9Vc2Vycy9saXRzZWxpdS9Eb2N1bWVudHMvUHJvdG90eXBlcy9sb2JlY2hhdDIvdml0ZS5jb25maWcuanNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJztcbmltcG9ydCByZWFjdCBmcm9tICdAdml0ZWpzL3BsdWdpbi1yZWFjdCc7XG5cbmV4cG9ydCBkZWZhdWx0IGRlZmluZUNvbmZpZyh7XG4gIHBsdWdpbnM6IFtyZWFjdCgpXSxcbiAgc2VydmVyOiB7XG4gICAgaG9zdDogJzEyNy4wLjAuMScsXG4gICAgcG9ydDogNTE3NixcbiAgICBzdHJpY3RQb3J0OiB0cnVlLFxuICAgIHByb3h5OiB7XG4gICAgICAnL2FwaSc6ICdodHRwOi8vbG9jYWxob3N0Ojg3ODcnLFxuICAgIH0sXG4gICAgd2F0Y2g6IHtcbiAgICAgIC8vIEF2b2lkIHNwdXJpb3VzIHJlc3RhcnRzIHdoZW4gZWRpdG9ycy9zeW5jIHRvb2xzIHRvdWNoIGVudi9jb25maWcvY2FjaGUgZm9sZGVycy5cbiAgICAgIGlnbm9yZWQ6IFsnKiovLmVudionLCAnKiovdml0ZS5jb25maWcuanMnLCAnKiovLnZlbnYvKionLCAnKiovbm9kZV9tb2R1bGVzLy52aXRlLyoqJ10sXG4gICAgfSxcbiAgfSxcbn0pO1xuIl0sCiAgIm1hcHBpbmdzIjogIjtBQUE0VCxTQUFTLG9CQUFvQjtBQUN6VixPQUFPLFdBQVc7QUFFbEIsSUFBTyxzQkFBUSxhQUFhO0FBQUEsRUFDMUIsU0FBUyxDQUFDLE1BQU0sQ0FBQztBQUFBLEVBQ2pCLFFBQVE7QUFBQSxJQUNOLE1BQU07QUFBQSxJQUNOLE1BQU07QUFBQSxJQUNOLFlBQVk7QUFBQSxJQUNaLE9BQU87QUFBQSxNQUNMLFFBQVE7QUFBQSxJQUNWO0FBQUEsSUFDQSxPQUFPO0FBQUE7QUFBQSxNQUVMLFNBQVMsQ0FBQyxZQUFZLHFCQUFxQixlQUFlLDBCQUEwQjtBQUFBLElBQ3RGO0FBQUEsRUFDRjtBQUNGLENBQUM7IiwKICAibmFtZXMiOiBbXQp9Cg==
