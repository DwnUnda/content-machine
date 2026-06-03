# WordPress Draft Upload

This script uploads completed articles to WordPress as draft posts using the REST API.

## Prerequisites

Ensure your `.env` file has these WordPress credentials configured:

```env
WORDPRESS_BASE_URL=https://example.com
WORDPRESS_USERNAME=your-app-user
WORDPRESS_APP_PASSWORD=your-app-password
```

**Important:**
- Use an **Application Password**, not your regular WordPress password
- Never commit `.env` to version control
- The user must have permission to create posts in WordPress

## Generate Application Password

1. Log in to WordPress admin
2. Go to **Users** → Your profile
3. Scroll to **Application Passwords**
4. Enter an app name (e.g., "Content Machine")
5. Click **Create Application Password**
6. Copy the generated password to `.env` as `WORDPRESS_APP_PASSWORD`

## Usage

### Upload a single article:

```bash
npm run upload:wordpress -- --article "D:\Software\content-machine\Completed-Articles\articles\ARTICLE_FOLDER_NAME"
```

### Example:

```bash
npm run upload:wordpress -- --article "D:\Software\content-machine\Completed-Articles\articles\article-4-how-to-prevent-mould-in-bedrooms"
```

## How It Works

1. **Reads article source**
   - Looks for `drafts/latest.json` or `drafts/draft-v3-final.json`
   - Extracts `draft_markdown`, `slug`, `seo_title`, `meta_description`, `excerpt`

2. **Converts to HTML**
   - Uses the same Markdown-to-HTML converter as `export:html`
   - Generates clean WordPress-ready HTML

3. **Saves HTML locally**
   - Saves as `{slug}.html` in the article folder

4. **Creates WordPress draft**
   - Sends POST request to `/wp-json/wp/v2/posts`
   - Sets status to `draft` (never published)
   - Uses `seo_title` as post title
   - Uses article `slug` if available
   - Includes `excerpt` from JSON

5. **Returns WordPress post ID**
   - Shows direct edit link
   - Stores post ID in enhanced JSON

## Output

### Success:

```
Uploading article to WordPress...

Local source JSON: D:\Software\content-machine\Completed-Articles\articles\article-4-how-to-prevent-mould-in-bedrooms\drafts\latest.json
Generated HTML: D:\Software\content-machine\Completed-Articles\articles\article-4-how-to-prevent-mould-in-bedrooms\how-to-prevent-mould-in-bedrooms.html
WordPress endpoint: https://homedrylab.com/wp-json/wp/v2/posts

Post data:
  Title: How to Prevent Mould in Bedrooms | Australian Guide
  Slug: how-to-prevent-mould-in-bedrooms
  Status: draft
  Excerpt: ✓ included

Meta description: Practical ways to prevent mould in bedrooms... (add manually in WordPress)

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

## Post Metadata

### Fields sent to WordPress:

- **title** - From `seo_title` in JSON, or first H1 from markdown
- **content** - Converted HTML
- **status** - Always `draft`
- **slug** - From JSON slug field (if available)
- **excerpt** - From JSON excerpt field (if available)

### Fields NOT sent (manual work):

- **meta_description** - Printed in console, add manually to WordPress SEO tab or plugin
- **Featured image** - Requires separate upload
- **Categories/Tags** - Not automated yet
- **Yoast/Rank Math metadata** - Can be added later

## Authentication

Uses **Basic Auth** with Application Password:
- Username: `WORDPRESS_USERNAME` from .env
- Password: `WORDPRESS_APP_PASSWORD` from .env
- Never printed in console output for security

## Files Generated/Modified

- ✓ `{slug}.html` - WordPress-ready HTML (created or overwritten)
- ✓ `article.with-html.json` - Enhanced JSON with `wordpress_post_id` added
- ✓ Original `.json` and `.md` files - Never modified

## Validation Checklist

After upload, the script verifies:
- ✓ HTML file created locally
- ✓ WordPress draft post created
- ✓ Post status is `draft` (not published)
- ✓ Post ID returned
- ✓ Edit/view URLs available
- ✓ Enhanced JSON saved with post ID

## Common Errors

### 401 Unauthorized

**Problem:** WordPress authentication failed

**Solutions:**
1. Verify credentials in `.env` file
2. Ensure `WORDPRESS_USERNAME` matches the user creating the app password
3. Check that Application Password was created (not regular password)
4. Verify WordPress REST API is enabled (should be by default)
5. Check user has permission to create posts

### 403 Forbidden

**Problem:** User doesn't have permission to create posts

**Solutions:**
1. Check user role in WordPress (must have at least "Editor" or "Author")
2. Verify user hasn't been restricted
3. Check if site has additional security plugins blocking API

### Connection timeout

**Problem:** Can't reach WordPress site

**Solutions:**
1. Verify `WORDPRESS_BASE_URL` is correct in `.env`
2. Check internet connection
3. Verify WordPress site is online
4. Check firewall/security rules

## Limitations & Notes

- **One article at a time** - Script only uploads single articles (prevent accidental batch uploads)
- **Draft only** - Posts are always created as draft, never published
- **No image embedding** - Images in markdown are preserved as HTML but not auto-uploaded
- **SEO metadata** - `meta_description` is shown in console for manual copy/paste to SEO plugins
- **No Elementor** - This is plain WordPress post content, not Elementor layouts
- **No overwrite protection** - If you upload the same article twice, it creates a new post (no update/merge)

## Next Steps

To extend this feature:

1. **Update existing posts** - Add `--post-id` flag to update draft instead of creating new
2. **Batch upload** - Add `--batch` flag for multiple articles (with confirmation)
3. **SEO metadata** - Integrate with Yoast/Rank Math API to set meta description
4. **Featured images** - Auto-find and upload first image from research files
5. **Categories/Tags** - Read from article metadata and apply to WordPress
6. **Publish workflow** - Add approval step before publishing to WordPress

## Security Notes

- ✓ Never print `WORDPRESS_APP_PASSWORD` to console
- ✓ Always use Application Passwords, not account passwords
- ✓ .env file is in .gitignore (never committed)
- ✓ Scripts only read from .env, never write credentials
- ✓ No secrets in enhanced JSON or HTML files
- ✓ HTML content is sanitized (< > " ' & escaped)
