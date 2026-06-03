"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { api } from "@/lib/api";
import { Product } from "@/types";


export default function ProductDetailPage() {
  const params = useParams<{ id: string }>();
  const productId = Number(params.id);
  const [product, setProduct] = useState<Product | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.getProduct(productId).then(setProduct).catch((err) => setError(err.message));
  }, [productId]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    const form = new FormData(event.currentTarget);
    const toList = (value: string) =>
      value
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0);
    try {
      const updated = await api.updateProduct(productId, {
        name: String(form.get("name") || ""),
        brand: String(form.get("brand") || ""),
        category: String(form.get("category") || ""),
        role: String(form.get("role") || ""),
        product_url: String(form.get("product_url") || ""),
        personally_tested: form.get("personally_tested") === "on",
        model_number: String(form.get("model_number") || ""),
        retailer_domain: String(form.get("retailer_domain") || ""),
        price_text: String(form.get("price_text") || ""),
        capacity_text: String(form.get("capacity_text") || ""),
        tank_size_text: String(form.get("tank_size_text") || ""),
        noise_level_text: String(form.get("noise_level_text") || ""),
        power_use_text: String(form.get("power_use_text") || ""),
        warranty_text: String(form.get("warranty_text") || ""),
        drainage_text: String(form.get("drainage_text") || ""),
        room_size_text: String(form.get("room_size_text") || ""),
        review_rating_text: String(form.get("review_rating_text") || ""),
        review_count_text: String(form.get("review_count_text") || ""),
        description_snippet: String(form.get("description_snippet") || ""),
        common_positives: String(form.get("common_positives") || ""),
        common_complaints: String(form.get("common_complaints") || ""),
        who_should_buy: String(form.get("who_should_buy") || ""),
        who_should_avoid: String(form.get("who_should_avoid") || ""),
        best_for: String(form.get("best_for") || ""),
        bottom_line: String(form.get("bottom_line") || ""),
        notes: String(form.get("notes") || ""),
        // Review-led product analysis layer.
        manufacturer_url: String(form.get("manufacturer_url") || ""),
        retailer_urls: toList(String(form.get("retailer_urls") || "")),
        positive_review_patterns: String(form.get("positive_review_patterns") || ""),
        negative_review_patterns: String(form.get("negative_review_patterns") || ""),
        reliability_concerns: String(form.get("reliability_concerns") || ""),
        key_specs: toList(String(form.get("key_specs") || "")),
        price_range_text: String(form.get("price_range_text") || ""),
        australian_availability: String(form.get("australian_availability") || ""),
        review_methodology_notes: String(form.get("review_methodology_notes") || ""),
      });
      setProduct(updated);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update product.");
    } finally {
      setSaving(false);
    }
  }

  if (error && !product) return <div className="message error">{error}</div>;
  if (!product) return <div className="panel muted">Loading product...</div>;

  return (
    <form className="panel form-grid" onSubmit={onSubmit}>
      <div className="field">
        <label htmlFor="name">Name</label>
        <input defaultValue={product.name} id="name" name="name" />
      </div>
      <div className="field">
        <label htmlFor="brand">Brand</label>
        <input defaultValue={product.brand || ""} id="brand" name="brand" />
      </div>
      <div className="field">
        <label htmlFor="category">Category</label>
        <input defaultValue={product.category || ""} id="category" name="category" />
      </div>
      <div className="field">
        <label htmlFor="role">Role (e.g. Best Budget)</label>
        <input defaultValue={product.role || ""} id="role" name="role" />
      </div>
      <div className="field">
        <label htmlFor="product_url">Product URL</label>
        <input defaultValue={product.product_url || ""} id="product_url" name="product_url" />
      </div>
      <div className="field">
        <label htmlFor="personally_tested">Personally tested</label>
        <input defaultChecked={product.personally_tested} id="personally_tested" name="personally_tested" type="checkbox" />
      </div>
      <div className="field">
        <label htmlFor="model_number">Model</label>
        <input defaultValue={product.model_number || ""} id="model_number" name="model_number" />
      </div>
      <div className="field">
        <label htmlFor="retailer_domain">Retailer / domain</label>
        <input defaultValue={product.retailer_domain || ""} id="retailer_domain" name="retailer_domain" />
      </div>
      <div className="field">
        <label htmlFor="price_text">Price</label>
        <input defaultValue={product.price_text || ""} id="price_text" name="price_text" />
      </div>
      <div className="field">
        <label htmlFor="capacity_text">Capacity</label>
        <input defaultValue={product.capacity_text || ""} id="capacity_text" name="capacity_text" />
      </div>
      <div className="field">
        <label htmlFor="tank_size_text">Tank size</label>
        <input defaultValue={product.tank_size_text || ""} id="tank_size_text" name="tank_size_text" />
      </div>
      <div className="field">
        <label htmlFor="noise_level_text">Noise level</label>
        <input defaultValue={product.noise_level_text || ""} id="noise_level_text" name="noise_level_text" />
      </div>
      <div className="field">
        <label htmlFor="power_use_text">Power use</label>
        <input defaultValue={product.power_use_text || ""} id="power_use_text" name="power_use_text" />
      </div>
      <div className="field">
        <label htmlFor="warranty_text">Warranty</label>
        <input defaultValue={product.warranty_text || ""} id="warranty_text" name="warranty_text" />
      </div>
      <div className="field">
        <label htmlFor="drainage_text">Drainage option</label>
        <input defaultValue={product.drainage_text || ""} id="drainage_text" name="drainage_text" />
      </div>
      <div className="field">
        <label htmlFor="room_size_text">Room size claim</label>
        <input defaultValue={product.room_size_text || ""} id="room_size_text" name="room_size_text" />
      </div>
      <div className="field">
        <label htmlFor="review_rating_text">Review rating</label>
        <input defaultValue={product.review_rating_text || ""} id="review_rating_text" name="review_rating_text" />
      </div>
      <div className="field">
        <label htmlFor="review_count_text">Review count</label>
        <input defaultValue={product.review_count_text || ""} id="review_count_text" name="review_count_text" />
      </div>
      <div className="field-full">
        <label htmlFor="description_snippet">Product description snippet</label>
        <textarea defaultValue={product.description_snippet || ""} id="description_snippet" name="description_snippet" />
      </div>
      <div className="field-full">
        <label htmlFor="common_positives">Common positives</label>
        <textarea defaultValue={product.common_positives || ""} id="common_positives" name="common_positives" />
      </div>
      <div className="field-full">
        <label htmlFor="common_complaints">Common complaints</label>
        <textarea defaultValue={product.common_complaints || ""} id="common_complaints" name="common_complaints" />
      </div>
      <div className="field-full">
        <label htmlFor="who_should_buy">Who should buy it</label>
        <textarea defaultValue={product.who_should_buy || ""} id="who_should_buy" name="who_should_buy" />
      </div>
      <div className="field-full">
        <label htmlFor="who_should_avoid">Who should avoid it</label>
        <textarea defaultValue={product.who_should_avoid || ""} id="who_should_avoid" name="who_should_avoid" />
      </div>
      <div className="field-full">
        <label htmlFor="best_for">Best for</label>
        <textarea defaultValue={product.best_for || ""} id="best_for" name="best_for" />
      </div>
      <div className="field-full">
        <label htmlFor="bottom_line">Bottom line</label>
        <textarea defaultValue={product.bottom_line || ""} id="bottom_line" name="bottom_line" />
      </div>
      <div className="field">
        <label htmlFor="manufacturer_url">Manufacturer URL</label>
        <input defaultValue={product.manufacturer_url || ""} id="manufacturer_url" name="manufacturer_url" />
      </div>
      <div className="field">
        <label htmlFor="price_range_text">Price range</label>
        <input defaultValue={product.price_range_text || ""} id="price_range_text" name="price_range_text" />
      </div>
      <div className="field">
        <label htmlFor="australian_availability">Australian availability</label>
        <input defaultValue={product.australian_availability || ""} id="australian_availability" name="australian_availability" />
      </div>
      <div className="field-full">
        <label htmlFor="retailer_urls">Retailer URLs (one per line)</label>
        <textarea
          defaultValue={(product.retailer_urls || [])
            .map((entry) => (typeof entry === "string" ? entry : entry?.url || ""))
            .filter(Boolean)
            .join("\n")}
          id="retailer_urls"
          name="retailer_urls"
        />
        <p className="muted small-copy">Editing here saves plain URLs and drops AI-found prices/verification; re-run AI research to restore them.</p>
      </div>
      <div className="field-full">
        <label htmlFor="key_specs">Key specs (one per line)</label>
        <textarea defaultValue={(product.key_specs || []).join("\n")} id="key_specs" name="key_specs" />
      </div>
      <div className="field-full">
        <label htmlFor="positive_review_patterns">Positive review patterns</label>
        <textarea defaultValue={product.positive_review_patterns || ""} id="positive_review_patterns" name="positive_review_patterns" />
      </div>
      <div className="field-full">
        <label htmlFor="negative_review_patterns">Negative review patterns</label>
        <textarea defaultValue={product.negative_review_patterns || ""} id="negative_review_patterns" name="negative_review_patterns" />
      </div>
      <div className="field-full">
        <label htmlFor="reliability_concerns">Reliability concerns</label>
        <textarea defaultValue={product.reliability_concerns || ""} id="reliability_concerns" name="reliability_concerns" />
      </div>
      <div className="field-full">
        <label htmlFor="review_methodology_notes">Review methodology notes</label>
        <textarea defaultValue={product.review_methodology_notes || ""} id="review_methodology_notes" name="review_methodology_notes" />
      </div>
      <div className="field-full">
        <label htmlFor="notes">Notes</label>
        <textarea defaultValue={product.notes || ""} id="notes" name="notes" />
      </div>
      {error ? <div className="field-full message error">{error}</div> : null}
      <div className="field-full">
        <button className="button" disabled={saving} type="submit">{saving ? "Saving..." : "Save product"}</button>
      </div>
    </form>
  );
}
