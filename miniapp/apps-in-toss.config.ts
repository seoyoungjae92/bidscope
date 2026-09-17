import { defineConfig } from '@apps-in-toss/web-framework/config';

export default defineConfig({
  // 콘솔 등록 시 확정한 appName. 등록 후 변경 불가라 여기도 같이 맞춘다.
  appName: 'bidscope',
  brand: {
    primaryColor: '#3182F6',
  },
  webView: {},
  permissions: [],
  webBundleDir: 'dist',
});
