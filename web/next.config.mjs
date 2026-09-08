/** @type {import('next').NextConfig} */
// GitHub Pages serves the site under /qualto; Vercel serves it at the domain
// root. basePath is enabled only when explicitly requested.
const isPages = process.env.QUALTO_BASE_PATH === "1";

const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  ...(isPages ? { basePath: "/qualto", assetPrefix: "/qualto/" } : {}),
};

export default nextConfig;

