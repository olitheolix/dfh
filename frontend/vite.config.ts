import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [
        react(),
    ],
    server: {
        port: 5000,
        proxy: {
            // Proxy all API requests to the backend.
            '/api': {
                target: 'http://localhost:5001',
                changeOrigin: true,
            },
            '/data': {
                target: 'http://localhost:5002',
                changeOrigin: true,
            }
        }
    }
});
