"use client";

import Link from "next/link";

import { EntityManager } from "@/components/entity-manager";
import { api } from "@/lib/api";
import { Product } from "@/types";


export default function ProductsPage() {
  return (
    <div className="stack">
      <section>
        <div className="brand-kicker">Product evidence</div>
        <div className="page-title">Products</div>
      </section>
      <EntityManager<Product>
        title="product"
        fields={[
          { key: "name", label: "Name" },
          { key: "brand", label: "Brand" },
          { key: "category", label: "Category" },
          { key: "product_url", label: "Product URL" },
          { key: "personally_tested", label: "Personally tested", type: "checkbox" },
          { key: "notes", label: "Notes", type: "textarea" },
        ]}
        list={api.listProducts}
        create={api.createProduct}
        renderItem={(item) => (
          <>
            <div className="toolbar">
              <strong>{item.name}</strong>
              <Link href={`/products/${item.id}`}>Open</Link>
            </div>
            <div className="muted">{item.brand || "No brand"} · {item.category || "No category"}</div>
          </>
        )}
      />
    </div>
  );
}
