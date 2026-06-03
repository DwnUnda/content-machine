# WordPress Article CSS

Generated drafts wrap their body in `<div class="hdl-article-content">` and use a
small set of `hdl-*` classes (`.hdl-quick-answer`, `.hdl-faq-section`,
`.hdl-faq-item`, `.hdl-table-wrap`, `.hdl-table`, `.hdl-image-block`,
`.hdl-callout`). No inline per-element styles are used.

## Heading alignment & weight (scoped style block)

To guarantee consistent headings on the frontend even before the theme CSS is
updated, the uploader injects a tiny **scoped** `<style>` block at the top of the
article body (see `buildScopedStyleBlock()` in
`scripts/wordpress-upload-utils.js`). This is the exact CSS generated:

```css
.hdl-article-content { color: #111; }
.hdl-article-content h2 { text-align: center; font-weight: 700; color: #111; }
.hdl-article-content h3 { text-align: left; font-weight: 700; color: #111; }
.hdl-article-content p,
.hdl-article-content li,
.hdl-article-content td,
.hdl-article-content th { text-align: left; color: #111; }
.hdl-table th { font-weight: 700; }
.hdl-article-content figure.hdl-image-block { margin-left: auto; margin-right: auto; text-align: center; }
.hdl-article-content figure.hdl-image-block img { display: block; margin-left: auto; margin-right: auto; }
.hdl-article-content figure.hdl-image-block figcaption { text-align: center; }
```

This block is scoped to `.hdl-article-content`, so it only affects our article
body and never the rest of the site. It guarantees:

- H2 headings are **centered and bold**
- H3 headings are **left-aligned and bold**
- paragraphs, lists, and table cells stay **left-aligned**
- all article text is **near-black (#111)**
- images (`.hdl-image-block` figures) and their captions are **centered**

No inline per-heading styles are used. The fuller styling below is still
recommended for spacing, table borders, and image blocks.

## Centering the WordPress post title (H1)

The WordPress post title is the article's **only** H1, and it lives **outside**
`.hdl-article-content` (it is rendered by the WordPress theme, not by our HTML).
Because of that, the scoped block above cannot style it. There is no safe
project-level hook to inject site-wide title CSS without touching the theme or
Elementor, so this must be pasted manually into
**WordPress → Appearance → Customize → Additional CSS**:

```css
.single-post .entry-title,
.single-post h1.entry-title,
.single-post .wp-block-post-title,
.single-post h1.wp-block-post-title,
body.single-post h1 {
  text-align: center;
  font-weight: 700;
  color: #111;
}
```

## Recommended Additional CSS (manual)

For the full polished look (spacing, colours, table styling, image blocks), paste
the following into **WordPress → Appearance → Customize → Additional CSS**. This is
optional — the scoped `<style>` block above already handles heading alignment — but
it is the recommended one-time manual setup.

```css
.hdl-article-content {
  max-width: 820px;
  margin: 0 auto;
  color: #111;
  font-size: 18px;
  line-height: 1.75;
}

.hdl-article-content p,
.hdl-article-content li,
.hdl-article-content td,
.hdl-article-content th {
  color: #111;
}

.hdl-article-content p,
.hdl-article-content ul,
.hdl-article-content ol,
.hdl-article-content blockquote,
.hdl-article-content .hdl-table-wrap,
.hdl-article-content .hdl-image-block {
  margin-top: 0;
  margin-bottom: 1.2em;
}

.hdl-article-content h2 {
  text-align: center;
  color: #111;
  margin-top: 2.4em;
  margin-bottom: 0.8em;
  font-size: 1.65em;
  line-height: 1.25;
}

.hdl-article-content h3 {
  text-align: left;
  color: #111;
  margin-top: 1.6em;
  margin-bottom: 0.55em;
  font-size: 1.25em;
  line-height: 1.3;
}

.hdl-article-content ul,
.hdl-article-content ol {
  color: #111;
  padding-left: 1.4em;
}

.hdl-article-content a {
  color: #0b5cad;
  text-decoration: underline;
}

.hdl-quick-answer,
.hdl-faq-section,
.hdl-faq-item {
  color: #111;
}

.hdl-table-wrap {
  overflow-x: auto;
  margin: 24px 0;
}

.hdl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.94em;
}

.hdl-table th,
.hdl-table td {
  text-align: left;
  color: #111;
  border: 1px solid #ddd;
  padding: 12px 14px;
  vertical-align: top;
}

.hdl-table th {
  font-weight: 700;
  background: #f5f5f5;
}

.hdl-table tr:nth-child(even) {
  background: #fafafa;
}

.hdl-image-block {
  margin: 32px 0;
}

.hdl-image-block img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 12px;
}

.hdl-image-block figcaption {
  color: #555;
  text-align: center;
  margin-top: 8px;
  font-size: 0.92em;
  line-height: 1.45;
}
```
