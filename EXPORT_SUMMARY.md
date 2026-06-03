# Article HTML Export - Implementation Summary

## Task Completed ✓

Added a focused article export step that converts completed article Markdown into clean WordPress-ready HTML.

---

## Files Created

### 1. `scripts/export-html.js` (10.3 KB)
- **Purpose**: Main export script that converts Markdown to HTML
- **Language**: Node.js (JavaScript)
- **Dependencies**: None (uses only Node.js built-in modules)
- **Features**:
  - Scans article folders in `Completed-Articles/articles`
  - Prefers `.json` files with `draft_markdown` field
  - Falls back to `.md` files if JSON not available
  - Converts Markdown to WordPress-ready HTML
  - Saves HTML with slug-based filename (e.g., `how-to-prevent-mould-in-bedrooms.html`)
  - Creates enhanced JSON with `content_html` field
  - Provides detailed console output

### 2. `package.json` (Root level)
- **Purpose**: Project-level scripts and workspace configuration
- **Content**: Added `npm run export:html` script
- **Usage**: `npm run export:html`

### 3. `scripts/README.md` (4.9 KB)
- **Purpose**: Complete documentation for the export feature
- **Content**: Usage, features, CSS, examples, limitations

---

## How to Use

### Command 1: Using npm script (Recommended)
```bash
npm run export:html
```

### Command 2: Direct Node.js with custom path
```bash
node scripts/export-html.js "D:\Software\content-machine\Completed-Articles\articles"
```

---

## Example Output

```
Searching for articles in: D:\Software\content-machine\Completed-Articles\articles

Found 16 article folder(s).

✓ Exported: article-4-how-to-prevent-mould-in-bedrooms
  Source: article-4-how-to-prevent-mould-in-bedrooms/drafts/latest.json (JSON)
  Output: how-to-prevent-mould-in-bedrooms.html
  Path: D:\Software\content-machine\Completed-Articles\articles\article-4-how-to-prevent-mould-in-bedrooms\how-to-prevent-mould-in-bedrooms.html
  Enhanced JSON: article.with-html.json

⊘ Skipped: article-1-analysis-test
  Reason: No content found in source file

============================================================
Export complete: 2 exported, 14 skipped
============================================================
```

---

## Generated Files Location

**Where HTML is saved:**
```
D:\Software\content-machine\Completed-Articles\articles\
  └── {article-folder}\
      ├── {slug}.html                  ← Generated HTML (WordPress-ready)
      ├── article.with-html.json       ← Enhanced JSON with content_html
      └── [existing files preserved]
```

**Examples:**
- `article-4-how-to-prevent-mould-in-bedrooms/how-to-prevent-mould-in-bedrooms.html`
- `article-3-what-humidity-level-causes-mould-in-australian-homes/article.html`

---

## HTML Output Characteristics

### WordPress Compatibility ✓
- **No document wrapper** - contains only article body HTML
- **No `<html>`, `<head>`, `<body>` tags**
- **Directly pasteable** into WordPress post editor
- **Ready for WordPress REST API** `/wp-json/wp/v2/posts` content field

### Markdown Conversions ✓
| Markdown | HTML | Example |
|----------|------|---------|
| `# Heading 1` | `<h1>` | `<h1>How to Prevent Mould</h1>` |
| `## Heading 2` | `<h2>` | `<h2>Quick Answer</h2>` |
| `### Heading 3` | `<h3>` | `<h3>Subsection</h3>` |
| `**bold**` | `<strong>` | `<strong>important</strong>` |
| `*italic*` | `<em>` | `<em>emphasized</em>` |
| `[link](url)` | `<a href="">` | `<a href="https://...">link text</a>` |
| `- bullet` | `<ul><li>` | Unordered lists |
| `1. numbered` | `<ol><li>` | Ordered lists |
| `` `code` `` | `<code>` | `<code>variable</code>` |
| `\| table \|` | Table with wrapper | Proper HTML tables |
| `---` | `<hr>` | Horizontal rules |

### Table Structure ✓
All tables are properly wrapped and styled:

```html
<div class="hdl-table-wrap">
  <table class="hdl-table">
    <thead>
      <tr>
        <th>Header</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Data</td>
      </tr>
    </tbody>
  </table>
</div>
```

---

## WordPress CSS to Add

Add this to your WordPress theme or use WordPress Custom CSS:

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

---

## Data Sources (Priority Order)

1. **Primary**: `drafts/latest.json` with `draft_markdown` field
2. **Secondary**: `drafts/draft-v3-final.json` with `draft_markdown`
3. **Fallback**: Any `.md` file in article root folder

Metadata extracted from JSON (when available):
- `slug` - Used for HTML filename
- `seo_title` - Preserved in enhanced JSON
- `meta_description` - Preserved in enhanced JSON
- `excerpt` - Preserved in enhanced JSON

---

## Validation Checklist

✓ HTML files created successfully  
✓ `<h1>`, `<h2>`, `<h3>` tags properly generated  
✓ `<p>` tags for all paragraphs  
✓ `<strong>` for bold text  
✓ `<em>` for italic text  
✓ `<a href="">` for links  
✓ `<ul><li>` for bullet lists  
✓ `<ol><li>` for numbered lists  
✓ `<code>` for inline code  
✓ Tables wrapped in `hdl-table-wrap`  
✓ Tables have `hdl-table` class  
✓ Tables use proper `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>`  
✓ No raw Markdown table pipes in output  
✓ No full HTML document wrapper  
✓ No `<html>`, `<head>`, `<body>` tags  

---

## Preservation & Safety

✓ **Source files never modified** - All original `.json`, `.md`, and other files remain untouched  
✓ **Regeneration safe** - Running export again only overwrites the matching `.html` files  
✓ **Non-destructive** - Original article metadata and workflow data completely preserved  
✓ **Backwards compatible** - No changes to article generation, research pipeline, or existing outputs  

---

## Enhancement: article.with-html.json

When exporting from JSON source, an enhanced version is created:

**Original field structure preserved:**
- `draft_markdown` - Original Markdown content
- `slug` - Article slug
- `seo_title` - SEO title
- `meta_description` - Meta description
- `excerpt` - Article excerpt
- `version` - Version number
- `stage` - Stage (e.g., "final")

**New field added:**
- `content_html` - Full converted HTML content (26KB+ for typical articles)

**Purpose**: Enables WordPress integration to use HTML directly without re-conversion.

---

## Architecture Notes

### Design Decisions
1. **No external dependencies** - Uses only Node.js built-ins for reliability and portability
2. **In-place generation** - HTML saved directly to article folders (alongside source files)
3. **Additive only** - Never modifies source files or existing outputs
4. **Slug-based naming** - Uses JSON slug field for predictable, SEO-friendly filenames
5. **Simple & portable** - Single script, zero setup, runs anywhere Node.js is available

### Not Implemented (As Requested)
- ❌ WordPress upload/API integration
- ❌ Elementor JSON generation
- ❌ Draft/publish state management
- ❌ Featured image handling
- ❌ Category/tag assignment
- ❌ Preview HTML generation (would add complexity)

---

## Testing Results

**Test run on 16 article folders:**
- ✓ 2 exported successfully (with complete metadata)
- ✓ 14 skipped (test/draft articles with no final content)
- ✓ 0 errors
- ✓ All original files preserved
- ✓ HTML validated against all requirements

**Generated output verified:**
- ✓ `article-3-what-humidity-level-causes-mould-in-australian-homes/article.html` (27.5 KB)
- ✓ `article-4-how-to-prevent-mould-in-bedrooms/how-to-prevent-mould-in-bedrooms.html` (26.2 KB)
- ✓ Both enhanced JSON files created
- ✓ All HTML tags correct
- ✓ All Markdown converted properly
- ✓ WordPress compatibility verified

---

## Limitations & Notes

1. **Images** - Markdown image syntax `![alt](url)` is preserved in HTML but not embedded (WordPress requires separate upload)
2. **Code blocks** - Triple-backtick code blocks are preserved but syntax highlighting must be added in WordPress
3. **Complex Markdown** - Footnotes, definition lists, and other extensions are not supported
4. **Nested lists** - Deeply nested lists may not render perfectly (use single-level for best results)
5. **HTML in Markdown** - Raw HTML in source Markdown is preserved as-is (may need escaping for WordPress)

---

## Next Steps (Not Implemented)

To fully integrate with WordPress:
1. Create WordPress API client module
2. Add draft post creation from HTML
3. Set SEO title, meta description from JSON metadata
4. Add featured image upload handling
5. Create publish/update workflow
6. Add status tracking (draft/pending/published)

These are separate tasks and should be done in a follow-up implementation.

---

## Quick Reference

**Run the export:**
```bash
npm run export:html
```

**Find generated HTML:**
```
D:\Software\content-machine\Completed-Articles\articles\{article-folder}\{slug}.html
```

**Documentation:**
```
D:\Software\content-machine\scripts\README.md
```

**Script location:**
```
D:\Software\content-machine\scripts\export-html.js
```
