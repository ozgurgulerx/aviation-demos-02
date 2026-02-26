/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
  async rewrites() {
    return [
      {
        source: '/api/av/:path*',
        destination: `${process.env.BACKEND_URL || 'http://localhost:5002'}/api/av/:path*`,
      },
    ];
  },
};

export default nextConfig;
