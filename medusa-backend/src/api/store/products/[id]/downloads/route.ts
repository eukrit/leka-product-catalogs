import type { MedusaRequest, MedusaResponse } from "@medusajs/framework/http"
import { Modules } from "@medusajs/framework/utils"

/**
 * GET /store/products/:id/downloads
 * Returns product downloads (technical sheets, DWG files) from metadata.
 */
export async function GET(req: MedusaRequest, res: MedusaResponse) {
  const { id } = req.params

  const productService = req.scope.resolve(Modules.PRODUCT)
  const product = await productService.retrieveProduct(id)

  if (!product) {
    return res.status(404).json({ message: "Product not found" })
  }

  const metadata = product.metadata || {}
  const downloads = metadata.downloads || []

  res.json({
    product_id: id,
    downloads,
  })
}
