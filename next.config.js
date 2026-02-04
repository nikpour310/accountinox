const nextConfig = {
  reactStrictMode: true,
  experimental: {
    appDir: true
  },
  // produce a standalone output suitable for cPanel / Passenger deployments
  output: "standalone",
  images: {
    domains: ["cdn.example.com"]
  },
  productionBrowserSourceMaps: false
};

module.exports = nextConfig;