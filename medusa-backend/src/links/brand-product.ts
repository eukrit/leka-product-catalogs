import BrandModule from "../modules/brand"
import ProductModule from "@medusajs/medusa/product"
import { defineLink } from "@medusajs/framework/utils"

// One brand has many products; each product has exactly one brand.
// The link replaces the old "brand = sales channel" coupling so the cart
// is no longer brand-scoped.
export default defineLink(
  BrandModule.linkable.brand,
  {
    linkable: ProductModule.linkable.product,
    isList: true,
  }
)
