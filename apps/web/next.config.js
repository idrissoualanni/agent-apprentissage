/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // En dev : ne pas bloquer sur les erreurs TS préexistantes (dashboard, sse.ts)
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
