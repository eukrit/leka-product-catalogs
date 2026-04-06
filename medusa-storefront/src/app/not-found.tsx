import Link from "next/link"

export default function NotFound() {
  return (
    <div className="min-h-screen bg-leka-cream flex items-center justify-center">
      <div className="text-center">
        <div className="text-6xl text-gray-200 mb-4">404</div>
        <h1 className="text-2xl font-bold text-leka-navy mb-2">Page Not Found</h1>
        <p className="text-gray-500 mb-8">
          The page you are looking for does not exist.
        </p>
        <Link href="/" className="btn-primary">
          Back to Catalogs
        </Link>
      </div>
    </div>
  )
}
