export type PostType =
  | "informational_blog"
  | "money_post"
  | "single_product_review"
  | "product_comparison"
  | "best_x_for_y";

export const POST_TYPE_OPTIONS = [
  { label: "Informational Blog Post",  value: "informational_blog"    },
  { label: "Money Post / Buyer Guide", value: "money_post"            },
  { label: "Single Product Review",    value: "single_product_review" },
  { label: "Product Comparison",       value: "product_comparison"    },
  { label: "Best X For Y Post",        value: "best_x_for_y"          },
] as const;

/** Minimum draft-ready product cards required before drafting is permitted. */
export const POST_TYPE_MIN_PRODUCTS: Record<PostType, number> = {
  informational_blog:    0,
  money_post:            3,
  single_product_review: 1,
  product_comparison:    2,
  best_x_for_y:          3,
};

export function getMinProductsForPostType(postType: string): number {
  return POST_TYPE_MIN_PRODUCTS[postType as PostType] ?? 0;
}

export function isProductGated(postType: string): boolean {
  return getMinProductsForPostType(postType) > 0;
}

export function getPostTypeLabel(postType: string): string {
  return POST_TYPE_OPTIONS.find((o) => o.value === postType)?.label ?? postType;
}
