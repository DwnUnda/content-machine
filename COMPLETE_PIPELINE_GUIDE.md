# Article Export & WordPress Upload Pipeline

Complete guide for exporting articles as HTML and uploading to WordPress as draft posts.

## Quick Start

### 1. Export articles to HTML

```bash
npm run export:html
```

This converts all completed articles to WordPress-ready HTML and saves them locally.

### 2. Upload a draft to WordPress

```bash
npm run upload:wordpress -- --article "D:\Software\content-machine\Completed-Articles\articles\ARTICLE_FOLDER_NAME"
```

This uploads a single article as a WordPress draft post.

## Full Workflow

```
Article Source Files
  ├── drafts/latest.json (or draft-v3-final.json)
  │   ├── draft_markdown (Markdown content)
  │   ├── slug (URL slug)
  │   ├── seo_title (Post title)
  │   ├── meta_description (SEO meta)
  │   └── excerpt (Post excerpt)
  └── ✓ Original .md files (if present)
           ↓
    [export:html]
           ↓
    Generated Files (Saved Locally)
    ├── {slug}.html (WordPress-ready HTML)
    └── article.with-html.json (Enhanced JSON)
           ↓
    [upload:wordpress]
           ↓
    WordPress Draft Post Created
    ├── Post ID: 12345
    ├── Status: draft (ready for review)
    ├── Content: Clean HTML
    ├── Title: From seo_title
    ├── Slug: From JSON slug
    └── Excerpt: From JSON excerpt
           ↓
    Edit in WordPress Admin
    ├── Review content
    ├── Add featured image
    ├── Set categories/tags
    ├── Add SEO metadata
    └── Publish when ready
```

## Step 1: Export to HTML

### Command

```bash
npm run export:html
```

### What It Does

1. Scans `D:\Software\content-machine\Completed-Articles\articles\`
2. Finds all article folders
3. Reads `drafts/latest.json` or `.md` files
4. Converts Markdown to clean HTML
5. Saves `{slug}.html` in each article folder
6. Creates `article.with-html.json` with HTML content

### Output

```
Searching for articles in: D:\Software\content-machine\Completed-Articles\articles

Found 16 article folder(s).

✓ Exported: article-4-how-to-prevent-mould-in-bedrooms
  Source: article-4-how-to-prevent-mould-in-bedrooms/drafts/latest.json (JSON)
  Output: how-to-prevent-mould-in-bedrooms.html
  Path: D:\...\how-to-prevent-mould-in-bedrooms.html
  Enhanced JSON: article.with-html.json

⊘ Skipped: article-1-test-draft
  Reason: No content found in source file

Export complete: 15 exported, 1 skipped
```

### Generated Files

- `how-to-prevent-mould-in-bedrooms.html` - WordPress-ready HTML (25 KB)
- `article.with-html.json` - Enhanced JSON with `content_html` field

---

## Step 2: Upload to WordPress

### Prerequisites

Ensure `.env` has WordPress credentials:

```env
WORDPRESS_BASE_URL=https://homedrylab.com
WORDPRESS_USERNAME=Home Dry Lab Content Machine
WORDPRESS_APP_PASSWORD=iLWI 3MqX IuQY IYGj LwJh wKhl
```

**Note:** Create Application Password in WordPress Admin:
- Users → Your Profile → Application Passwords → Create

### Command

```bash
npm run upload:wordpress -- --article "D:\Software\content-machine\Completed-Articles\articles\article-4-how-to-prevent-mould-in-bedrooms"
```

### What It Does

1. Reads article JSON
2. Extracts metadata (title, slug, excerpt, content)
3. Converts markdown to HTML (same as export:html)
4. Saves HTML locally
5. Authenticates with WordPress (Application Password)
6. POSTs to `/wp-json/wp/v2/posts` as draft
7. Stores WordPress post ID locally
8. Shows edit/view URLs

### Output

```
Uploading article to WordPress...

Local source JSON: D:\...\article-4-how-to-prevent-mould-in-bedrooms\drafts\latest.json
Generated HTML: D:\...\how-to-prevent-mould-in-bedrooms.html
WordPress endpoint: https://homedrylab.com/wp-json/wp/v2/posts

Post data:
  Title: How to Prevent Mould in Bedrooms | Australian Guide
  Slug: how-to-prevent-mould-in-bedrooms
  Status: draft
  Excerpt: ✓ included

Meta description: Practical ways to prevent mould in bedrooms...
(Note: Add this manually to WordPress SEO tab or plugin)

Authenticating with WordPress API...

✓ Draft post created successfully!

WordPress draft post ID: 12345
Edit URL: https://homedrylab.com/wp-admin/post.php?post=12345&action=edit
View URL: https://homedrylab.com/?p=12345
Status: draft (ready for review, not published)

Enhanced JSON saved: article.with-html.json
  (includes content_html and wordpress_post_id)

========================================
Upload complete. Post ID: 12345
========================================
```

### Result in WordPress

1. New **Draft** post created (not published)
2. Post ID: 12345
3. Can be found in WordPress Admin → Posts → Draft
4. Ready for:
   - Content review
   - Featured image upload
   - Category/tag assignment
   - SEO metadata (Yoast/Rank Math)
   - Final editing
   - Publishing

---

## HTML Output Format

### What Gets Converted

| Markdown | HTML |
|----------|------|
| `# Heading 1` | `<h1>Heading 1</h1>` |
| `## Heading 2` | `<h2>Heading 2</h2>` |
| `**bold**` | `<strong>bold</strong>` |
| `*italic*` | `<em>italic</em>` |
| `[link](url)` | `<a href="url">link</a>` |
| `- bullet` | `<ul><li>bullet</li></ul>` |
| `1. numbered` | `<ol><li>numbered</li></ol>` |
| `` `code` `` | `<code>code</code>` |
| Markdown table | Proper HTML table with classes |

### Table Structure

```html
<div class="hdl-table-wrap">
  <table class="hdl-table">
    <thead>
      <tr><th>Header 1</th></tr>
    </thead>
    <tbody>
      <tr><td>Data 1</td></tr>
    </tbody>
  </table>
</div>
```

### WordPress CSS (Add to theme)

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

## Data Flow

### Export Process

```
JSON Source File
  ├── draft_markdown → HTML conversion
  ├── slug → filename
  ├── seo_title → preserved
  ├── meta_description → preserved
  └── excerpt → preserved
              ↓
          HTML File
      (WordPress ready)
```

### Upload Process

```
Article JSON
  ├── draft_markdown → Convert to HTML
  ├── slug → POST slug parameter
  ├── seo_title → POST title parameter
  ├── excerpt → POST excerpt parameter
  └── meta_description → Console output (manual)
              ↓
    WordPress REST API
    /wp-json/wp/v2/posts
              ↓
      POST request with:
      ├── title
      ├── content (HTML)
      ├── status: "draft"
      ├── slug
      └── excerpt
              ↓
      WordPress Draft Post
      ├── ID: 12345
      ├── Status: draft
      └── Ready for review
```

---

## Post-Upload Workflow in WordPress

### In WordPress Admin

1. Go to Posts → All Posts (or Drafts filter)
2. Find your newly created draft post
3. Click "Edit"
4. Complete the following:

#### Content Review
- Read and check generated HTML
- Edit if needed
- Check formatting

#### Featured Image
- Click "Set featured image"
- Upload or select from media library
- (Note: Not auto-uploaded by scripts)

#### Categories & Tags
- Add relevant categories
- Add relevant tags
- (Note: Not auto-assigned by scripts)

#### SEO Metadata
- If using Yoast SEO:
  - Copy `meta_description` from console output
  - Paste into Yoast meta description field
  - Set focus keyword
  - Check readability

- If using Rank Math:
  - Click "Rank Math"
  - Enter target keyword
  - Add description from console output
  - Check SEO score

#### Preview
- Click "Preview" to see how it looks on site
- Make any final adjustments

#### Publish
- When satisfied, click "Publish"
- Post goes live

---

## Environment Setup

### WordPress Credentials in .env

**Must be configured before upload:**

```env
WORDPRESS_BASE_URL=https://homedrylab.com
WORDPRESS_USERNAME=Home Dry Lab Content Machine
WORDPRESS_APP_PASSWORD=iLWI 3MqX IuQY IYGj LwJh wKhl
```

### Creating Application Password

1. In WordPress: Users → Your Profile
2. Scroll to "Application Passwords"
3. Enter app name (e.g., "Content Machine")
4. Click "Create Application Password"
5. Copy the generated password
6. Paste into `.env` as `WORDPRESS_APP_PASSWORD`

**Security Note:**
- Use Application Passwords, not your regular WordPress password
- Each app has separate password
- Can revoke individual app passwords without changing main password
- Never share or commit passwords to version control

---

## File Organization

### After Export

```
article-4-how-to-prevent-mould-in-bedrooms/
├── drafts/
│   ├── latest.json           (original - untouched)
│   ├── latest.md
│   ├── draft-v3-final.json
│   └── draft-v3-final.md
├── research/
│   └── (various research files)
├── products/
│   └── (product data)
├── how-to-prevent-mould-in-bedrooms.html  ← Generated
├── article.with-html.json                 ← Generated
└── (other existing files)
```

### After Upload

```
article-4-how-to-prevent-mould-in-bedrooms/
├── drafts/
│   └── latest.json
├── how-to-prevent-mould-in-bedrooms.html
├── article.with-html.json                 ← Updated with wordpress_post_id
└── (other files)
```

---

## Error Handling

### Export Errors

| Issue | Solution |
|-------|----------|
| No articles found | Check path and folder structure |
| No JSON or markdown | Articles may be in progress (skipped) |
| HTML not generated | Check markdown syntax |

### Upload Errors

| Issue | Solution |
|-------|----------|
| 401 Unauthorized | Check WordPress credentials in .env |
| 403 Forbidden | User doesn't have post creation permission |
| Connection timeout | Verify WordPress site is online |
| No JSON found | Ensure article has completed draft |

---

## Batch Workflow

### Manual Batch Upload

Since upload is one-at-a-time (safe by design), to upload multiple articles:

```bash
# Article 1
npm run upload:wordpress -- --article "D:\...\article-4-how-to-prevent-mould-in-bedrooms"

# Article 2
npm run upload:wordpress -- --article "D:\...\article-3-what-humidity-level-causes-mould-in-australian-homes"

# Article 3
npm run upload:wordpress -- --article "D:\...\article-5-next-article"
```

Each creates a separate draft post.

### Recommended Workflow

1. **Export all** (once):
   ```bash
   npm run export:html
   ```

2. **Upload one at a time** (with review):
   ```bash
   npm run upload:wordpress -- --article "article-path"
   # Go to WordPress and review
   # Then upload next
   ```

3. **Review and publish** (in WordPress):
   - Go to WordPress admin
   - Review each draft
   - Publish when ready

---

## Security & Privacy

### Never Exposed
- ✓ WordPress password never printed
- ✓ Password only in .env file
- ✓ .env is in .gitignore
- ✓ No secrets in HTML or JSON outputs

### Safe by Design
- ✓ Draft posts only (never auto-published)
- ✓ Application Password (can be revoked)
- ✓ Single article at a time (prevents batch mistakes)
- ✓ User-authenticated (set in WordPress)

### File Protection
- ✓ Original source files never modified
- ✓ Only HTML and enhanced JSON generated
- ✓ All outputs are clean, no embedded secrets

---

## Documentation

### Quick Reference

- **Export guide**: `scripts/README.md`
- **Upload guide**: `scripts/UPLOAD-WORDPRESS.md`
- **Export summary**: `EXPORT_SUMMARY.md`
- **Upload summary**: `WORDPRESS_UPLOAD_SUMMARY.md`

### Script Locations

- **Export script**: `scripts/export-html.js`
- **Upload script**: `scripts/upload-wordpress.js`

### Sample Generated Files

- **HTML**: `{article-folder}/{slug}.html` (25 KB)
- **Enhanced JSON**: `{article-folder}/article.with-html.json` (50 KB)

---

## Troubleshooting

### "No content found in source file"

**Problem:** Article marked as skipped during export

**Solution:**
- Check `drafts/latest.json` exists
- Verify `draft_markdown` field is not empty
- If no markdown, article is not ready yet

### "WordPress upload failed: 401 Unauthorized"

**Problem:** Authentication failed

**Solutions:**
1. Check `.env` credentials are correct
2. Verify Application Password (not regular password)
3. Ensure user has Editor or Author role
4. Try creating password again

### "Sorry, you are not allowed to create posts as this user"

**Problem:** User doesn't have permission

**Solution:**
- Go to WordPress Users
- Check user role (must be Editor or Author minimum)
- Change role if needed

### HTML not displaying correctly

**Problem:** Tables or formatting appears wrong

**Solutions:**
- Add CSS to WordPress theme (see above)
- Check WordPress editor view (switch to Code editor)
- Verify HTML tags are present and properly nested

---

## Next Steps

### Coming Soon (Future Tasks)

1. **Batch upload** - Upload multiple articles with confirmation
2. **Post updates** - Update existing draft instead of creating new
3. **Publishing** - Publish workflow with approval step
4. **Featured images** - Auto-upload first image
5. **Categories/Tags** - Auto-assign from metadata
6. **SEO integration** - Send to Yoast/Rank Math
7. **Dashboard** - Show WordPress post status locally

---

## Summary

### Two-Command Pipeline

```bash
# Step 1: Export to HTML
npm run export:html

# Step 2: Upload to WordPress (one at a time)
npm run upload:wordpress -- --article "article-path"
```

### What's Automated
✓ Markdown → HTML conversion  
✓ Article metadata extraction  
✓ HTML file generation  
✓ WordPress draft post creation  
✓ WordPress post ID storage  

### What's Manual (by design)
✗ Featured image upload  
✗ Category/tag assignment  
✗ SEO metadata (copy/paste from console)  
✗ Final review and publishing  

### Result

Clean, WordPress-ready draft posts that are ready for review, editing, and publication.

---

**Ready to use:**

```bash
npm run export:html
npm run upload:wordpress -- --article "article-folder"
```
