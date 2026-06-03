#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { renderArticleHtml } = require('./article-html-renderer');

/**
 * Export articles as HTML
 */
async function exportArticlesToHtml(articlesDir) {
  console.log(`\nSearching for articles in: ${articlesDir}\n`);

  const articles = fs.readdirSync(articlesDir, { withFileTypes: true })
    .filter(dirent => dirent.isDirectory())
    .map(dirent => dirent.name);

  if (articles.length === 0) {
    console.log('No article folders found.');
    return;
  }

  console.log(`Found ${articles.length} article folder(s).\n`);

  let exported = 0;
  let skipped = 0;

  for (const article of articles) {
    const articlePath = path.join(articlesDir, article);
    const draftsPath = path.join(articlePath, 'drafts');
    
    // Look for latest.json or draft-v3-final.json
    const latestJsonPath = path.join(draftsPath, 'latest.json');
    const finalJsonPath = path.join(draftsPath, 'draft-v3-final.json');
    
    let jsonPath = null;
    let mdPath = null;

    if (fs.existsSync(latestJsonPath)) {
      jsonPath = latestJsonPath;
    } else if (fs.existsSync(finalJsonPath)) {
      jsonPath = finalJsonPath;
    } else {
      // Look for markdown file
      const files = fs.readdirSync(articlePath);
      const mdFile = files.find(f => f.endsWith('.md'));
      if (mdFile) {
        mdPath = path.join(articlePath, mdFile);
      }
    }

    if (!jsonPath && !mdPath) {
      console.log(`⊘ Skipped: ${article}`);
      console.log(`  Reason: No draft JSON or markdown file found\n`);
      skipped++;
      continue;
    }

    let markdown = '';
    let slug = 'article';
    let postType = 'informational_blog';
    let contentModules = [];
    let sourceFile = '';

    try {
      if (jsonPath) {
        const jsonData = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
        const articleJsonPath = path.join(articlePath, 'article.json');
        const articleData = fs.existsSync(articleJsonPath) ? JSON.parse(fs.readFileSync(articleJsonPath, 'utf8')) : {};
        markdown = jsonData.draft_markdown || '';
        slug = jsonData.slug || 'article';
        postType = jsonData.post_type || articleData.post_type || 'informational_blog';
        contentModules = Array.isArray(jsonData.content_modules) ? jsonData.content_modules : [];
        sourceFile = `${article}/drafts/${path.basename(jsonPath)} (JSON)`;
      } else if (mdPath) {
        markdown = fs.readFileSync(mdPath, 'utf8');
        slug = article.replace(/^article-\d+-/, '').replace(/[^a-z0-9-]/g, '-');
        sourceFile = `${article}/${path.basename(mdPath)} (Markdown)`;
      }

      if (!markdown) {
        console.log(`⊘ Skipped: ${article}`);
        console.log(`  Reason: No content found in source file\n`);
        skipped++;
        continue;
      }

      const html = renderArticleHtml(markdown, { post_type: postType, content_modules: contentModules });

      // Save HTML file
      const htmlFilename = `${slug}.html`;
      const htmlPath = path.join(articlePath, htmlFilename);

      fs.writeFileSync(htmlPath, html, 'utf8');

      console.log(`✓ Exported: ${article}`);
      console.log(`  Source: ${sourceFile}`);
      console.log(`  Output: ${htmlFilename}`);
      console.log(`  Path: ${htmlPath}\n`);

      // Create enhanced JSON with HTML (optional)
      if (jsonPath) {
        const jsonData = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
        const enhancedJson = {
          ...jsonData,
          post_type: postType,
          content_modules: contentModules,
          content_html: html
        };
        const enhancedPath = path.join(articlePath, 'article.with-html.json');
        fs.writeFileSync(enhancedPath, JSON.stringify(enhancedJson, null, 2), 'utf8');
        console.log(`  Enhanced JSON: article.with-html.json\n`);
      }

      exported++;
    } catch (error) {
      console.log(`✗ Error processing: ${article}`);
      console.log(`  Error: ${error.message}\n`);
      skipped++;
    }
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log(`Export complete: ${exported} exported, ${skipped} skipped`);
  console.log(`${'='.repeat(60)}\n`);

  return { exported, skipped };
}

// Main entry point
const articlesDir = process.argv[2] || path.join(__dirname, '..', 'Completed-Articles', 'articles');

exportArticlesToHtml(articlesDir).catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
