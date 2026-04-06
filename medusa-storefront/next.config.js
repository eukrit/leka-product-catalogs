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
    ],
  },
}

module.exports = nextConfig
