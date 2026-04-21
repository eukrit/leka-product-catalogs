/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "storage.googleapis.com",
        pathname: "/ai-agents-go-documents/**",
      },
      {
        protocol: "https",
        hostname: "zamowienia.vinci-play.pl",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "vinci-play.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "berlinerzone.b-cdn.net",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "www.eurotramp.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "rampline.no",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "www.rampline.no",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "4soft.cz",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "www.4soft.cz",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "www.vortex-intl.com",
        pathname: "/**",
      },
    ],
  },
  async redirects() {
    return [
      // Backwards-compat: old /vinciplay slug renamed to /vinci on 2026-04-21
      { source: "/vinciplay", destination: "/vinci", permanent: true },
      { source: "/vinciplay/:path*", destination: "/vinci/:path*", permanent: true },
    ]
  },
}

module.exports = nextConfig
