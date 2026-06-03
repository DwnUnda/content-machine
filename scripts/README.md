# Article Export to HTML

This script converts completed Markdown articles into WordPress-ready HTML.

## Usage

### From the project root:

```bash
npm run export:html
```

This will export all completed articles to HTML, using:
- `D:\Software\content-machine\Completed-Articles\articles` as the default source folder

### With custom source directory:

```bash
node scripts/export-html.js "D:\path\to\articles"
```

## How It Works

1. **Scans article folders** under `Completed-Articles/articles`
2. **Finds source content** - prefers `drafts/latest.json`, falls back to `drafts/draft-v3-final.json`, then `.md` files
3. **Extracts draft_markdown** from JSON (with metadata like slug, seo_title, meta_description)
4. **Converts Markdown to HTML** using built-in converter (no external dependencies)
5. **Generates output files**:
   - `{slug}.html` - WordPress-ready article HTML (if slug from JSON)
   - `article.html` - Fallback filename if no slug
   - `article.with-html.json` - Enhanced JSON with `content_html` field added

## Output

### HTML Features

- ✓ Markdown headings → HTML `<h1>`, `<h2>`, `<h3>`, `<h4>` tags
- ✓ Paragraphs → `<p>` tags
- ✓ Bold text (`**text**`) → `<strong>` tags
- ✓ Italic text (`*text*`) → `<em>` tags
- ✓ Links (`[text](url)`) → `<a href="">` tags
- ✓ Unordered lists (`- item`) → `<ul><li>` tags
- ✓ Ordered lists (`1. item`) → `<ol><li>` tags
- ✓ Inline code (`` `code` ``) → `<code>` tags
- ✓ Markdown tables → Proper HTML tables with `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>`
- ✓ Horizontal rules (`---`) → `<hr>` tags

### Table Structure

All tables are wrapped for CSS flexibility:

```html
<div class="hdl-table-wrap">
  <table class="hdl-table">
    <thead>
      <tr>
        <th>Header 1</th>
        <th>Header 2</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Data 1</td>
        <td>Data 2</td>
      </tr>
    </tbody>
  </table>
</div>
```

### Recommended WordPress CSS

Add this to your WordPress theme or custom CSS:

```css
.hdl-table-wrap {
  overflow-x: auto;
  margin: 24px 0;
}

.hdl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 16px;
}

.hdl-table th,
.hdl-table td {
  border: 1px solid #ddd;
  padding: 12px 14px;
  text-align: left;
  vertical-align: top;
}

.hdl-table th {
  font-weight: 700;
  background: #f5f5f5;
}

.hdl-table tr:nth-child(even) {
  background: #fafafa;
}
```

## Console Output Example

```
Searching for articles in: D:\Software\content-machine\Completed-Articles\articles

Found 2 article folder(s).

✓ Exported: article-4-how-to-prevent-mould-in-bedrooms
  Source: article-4-how-to-prevent-mould-in-bedrooms/drafts/latest.json (JSON)
  Output: how-to-prevent-mould-in-bedrooms.html
  Path: D:\Software\content-machine\Completed-Articles\articles\article-4-how-to-prevent-mould-in-bedrooms\how-to-prevent-mould-in-bedrooms.html
  Enhanced JSON: article.with-html.json

⊘ Skipped: article-1-test-draft
  Reason: No content found in source file

============================================================
Export complete: 1 exported, 1 skipped
============================================================
```

## Files Changed/Created

- ✓ `scripts/export-html.js` - Main export script (no dependencies)
- ✓ `package.json` - Root package.json with `npm run export:html` script
- ✓ Article HTML files - Saved to article folders as `{slug}.html`
- ✓ Enhanced JSON - Optional `article.with-html.json` with `content_html` field

## Important Notes

- **Source preference**: JSON `draft_markdown` is used when available (contains metadata like slug)
- **Markdown fallback**: `.md` files are used only if no usable JSON is found
- **Preservation**: Original `.md`, `.json`, and all other files are never modified
- **Regeneration**: Running the export again will safely overwrite only the matching `.html` files
- **WordPress compatible**: Output HTML is suitable for direct paste into WordPress post editor
- **No dependencies**: The converter uses only Node.js built-in modules

## Limitations

- Images in Markdown are preserved as-is but not embedded (WordPress requires separate upload)
- Complex Markdown extensions (e.g., footnotes, tables with merged cells) may not convert perfectly
- HTML is article-body only (no full document wrapper) for WordPress compatibility
- Code block syntax highlighting is preserved but not rendered (add language class manually in WordPress if needed)

## Validations

The script verifies:
- ✓ HTML file created successfully
- ✓ `<h2>` tags for `## ` Markdown headings
- ✓ `<h3>` tags for `### ` Markdown headings
- ✓ `<p>` tags for paragraphs
- ✓ No raw Markdown table pipes in output
- ✓ Tables wrapped in `hdl-table-wrap`
- ✓ Tables have `hdl-table` class
