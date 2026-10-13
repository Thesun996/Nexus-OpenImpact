const backendTarget = process.env.OPENIMPACT_API_PROXY_TARGET || "http://127.0.0.1:8000";

export default {
  server: {
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
};
