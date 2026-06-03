#!/usr/bin/env node

const http = require('http');
const https = require('https');

function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  };
  return String(text ?? '').replace(/[&<>"']/g, (match) => map[match]);
}

function slugify(value, fallback = 'visual-asset') {
  const text = String(value || '').trim().toLowerCase();
  const slug = text.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return slug || fallback;
}

function markdownToHtml(markdown, options = {}) {
  const {
    stripFirstH1 = false,
    stripHorizontalRules = false,
    wrapContainer = false,
    wrapSpecialSections = false,
    warnings = null,
  } = options;

  let source = String(markdown || '').replace(/\r\n?/g, '\n');
  const codeBlocks = [];
  source = source.replace(/```([\w-]+)?\n([\s\S]*?)```/g, (_match, language, code) => {
    const className = language ? ` class="language-${escapeHtml(language)}"` : '';
    codeBlocks.push(`<pre><code${className}>${escapeHtml(code.trimEnd())}</code></pre>`);
    return `__CODE_BLOCK_${codeBlocks.length - 1}__`;
  });

  const inlineCode = [];
  source = source.replace(/`([^`\n]+)`/g, (_match, code) => {
    inlineCode.push(`<code>${escapeHtml(code)}</code>`);
    return `__INLINE_CODE_${inlineCode.length - 1}__`;
  });

  const lines = source.split('\n');
  const result = [];
  let index = 0;
  let firstH1Removed = false;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    const nextLine = lines[index + 1] || '';

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (isTableStart(line, nextLine)) {
      const tableLines = [line, nextLine];
      index += 2;
      while (index < lines.length && isPotentialTableRow(lines[index])) {
        tableLines.push(lines[index]);
        index += 1;
      }
      const tableHtml = convertMarkdownTableToHtml(tableLines, warnings);
      if (tableHtml) {
        result.push(tableHtml);
      }
      continue;
    }

    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const content = escapeHtml(headingMatch[2].trim());
      if (level === 1 && stripFirstH1 && !firstH1Removed) {
        firstH1Removed = true;
      } else {
        result.push(`<h${level}>${content}</h${level}>`);
      }
      index += 1;
      continue;
    }

    if (isHorizontalRule(trimmed)) {
      if (!stripHorizontalRules) {
        result.push('<hr>');
      }
      index += 1;
      continue;
    }

    if (isListItem(line)) {
      const { html, nextIndex } = consumeList(lines, index);
      result.push(html);
      index = nextIndex;
      continue;
    }

    if (isBlockquoteLine(line)) {
      const { html, nextIndex } = consumeBlockquote(lines, index);
      result.push(html);
      index = nextIndex;
      continue;
    }

    result.push(consumeParagraph(lines, index, warnings));
    index = advanceParagraph(lines, index);
  }

  let html = result.join('\n');
  codeBlocks.forEach((block, blockIndex) => {
    html = html.replace(`__CODE_BLOCK_${blockIndex}__`, block);
  });
  inlineCode.forEach((code, codeIndex) => {
    html = html.replace(`__INLINE_CODE_${codeIndex}__`, code);
  });

  if (wrapSpecialSections) {
    html = wrapQuickAnswerSection(html);
    html = wrapFaqSection(html);
  }

  if (wrapContainer) {
    html = `${buildScopedStyleBlock()}\n<div class="hdl-article-content">\n${html}\n</div>`;
  }

  return html.trim();
}

/**
 * A small, reusable, scoped <style> block placed at the top of the article body.
 * Scoped to .hdl-article-content so it only affects our content, never the whole site.
 * Centres H2s and makes H2/H3 bold; keeps H3 / paragraphs / list items /
 * table cells left-aligned, and forces near-black text colour.
 * Also centres article images (.hdl-image-block figures and their captions).
 * This avoids inline per-heading styles and works even when the theme's
 * "Additional CSS" has not been updated. See docs/wordpress-article-css.md.
 */
function buildScopedStyleBlock() {
  return [
    '<style>',
    '.hdl-article-content { color: #111; max-width: 920px; margin: 0 auto; }',
    '.hdl-article-content > p:first-of-type { font-size: 1.08rem; line-height: 1.7; margin-bottom: 1.5rem; }',
    '.hdl-toc { margin: 2rem auto; padding: 1.25rem 1.5rem; max-width: 920px; border: 1px solid #e4d8ca; border-radius: 16px; background: #fbf7f2; }',
    '.hdl-toc h2 { margin: 0 0 1rem; text-align: center; font-weight: 700; color: #111; }',
    '.hdl-toc ul { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.7rem 0.8rem; align-items: stretch; }',
    '.hdl-toc li { margin: 0; }',
    '.hdl-toc a { display: flex; align-items: center; justify-content: center; min-height: 44px; padding: 0.6rem 0.9rem; border-radius: 999px; color: #111; text-decoration: none; border: 1px solid rgba(17, 17, 17, 0.18); background: #fffdf8; text-align: center; }',
    '.hdl-toc a:hover, .hdl-toc a:focus { border-bottom-color: rgba(17, 17, 17, 0.48); }',
    '.hdl-jump-links { margin: 1.1rem auto 2rem; max-width: 920px; }',
    '.hdl-jump-links ul { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.7rem 0.8rem; align-items: stretch; }',
    '.hdl-jump-links li { margin: 0; }',
    '.hdl-jump-links a { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; padding: 0.65rem 1rem; border-radius: 999px; border: 1px solid #e1d1be; background: #fffaf3; color: #2d261d; text-decoration: none; font-weight: 600; box-shadow: 0 8px 22px rgba(44, 36, 23, 0.05); text-align: center; }',
    '.hdl-jump-links a:hover, .hdl-jump-links a:focus { border-color: #cfae7c; background: #fff7ec; }',
    '.hdl-top-picks, .top-picks-grid { margin: 1.2rem 0 2rem; }',
    '.top-picks-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }',
    '.product-card.featured { padding: 1.2rem 1.15rem 1.1rem; border-radius: 20px; border: 1px solid #e6d7c6; background: linear-gradient(180deg, #fffdfa 0%, #f9f4ec 100%); box-shadow: 0 14px 34px rgba(44, 36, 23, 0.07); }',
    '.product-card.featured .badge { display: inline-flex; padding: 0.3rem 0.65rem; border-radius: 999px; background: #f0e0cb; color: #6f4d21; font-weight: 700; font-size: 0.82rem; letter-spacing: 0.01em; }',
    '.product-card.featured h3 { margin: 0.9rem 0 0.55rem; font-size: 1.3rem; }',
    '.product-card.featured ul { margin: 0.8rem 0 1rem; padding-left: 1.1rem; }',
    '.product-image-wrap { margin: 0.9rem 0 1rem; }',
    '.product-image-wrap img, .product-image-placeholder { width: 100%; aspect-ratio: 4 / 3; border-radius: 16px; }',
    '.product-image-wrap img { display: block; object-fit: cover; border: 1px solid #eadbc8; background: #fff; }',
    '.product-image-placeholder { display: flex; align-items: center; justify-content: center; padding: 1rem; border: 1px dashed #dcc7ad; background: linear-gradient(135deg, #f8f0e3 0%, #efe4d3 100%); color: #6e5431; font-weight: 700; text-align: center; }',
    '.product-card.featured .cta-button, .product-card.featured .read-review-link { display: inline-flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; border-radius: 999px; text-decoration: none; font-weight: 700; }',
    '.product-card.featured .cta-button { margin-top: 0.25rem; background: #2d5b43; color: #fff; }',
    '.product-card.featured .read-review-link { margin-top: 0.65rem; border: 1px solid #dbcab6; background: #fff; color: #2d261d; }',
    '.hdl-quick-answer, .hdl-methodology, .hdl-final-verdict, .hdl-comparison-module, .hdl-buyer-guide, .hdl-mistakes-module, .hdl-context-module, .hdl-performance-module, .hdl-specs-module, .hdl-review-fit-module { margin: 1.8rem 0 2rem; padding: 1.4rem 1.5rem; border-radius: 18px; }',
    '.hdl-quick-answer { background: linear-gradient(180deg, #fbf7f2 0%, #f5eee4 100%); border: 1px solid #e6d9ca; }',
    '.hdl-methodology { background: #f7f2eb; border: 1px solid #e6dbce; }',
    '.hdl-final-verdict { background: linear-gradient(180deg, #f4f0e7 0%, #efe5d7 100%); border: 1px solid #ddcfbc; }',
    '.hdl-comparison-module { background: #fffdfa; border: 1px solid #e8dbc9; box-shadow: 0 10px 28px rgba(44, 36, 23, 0.04); }',
    '.hdl-buyer-guide, .hdl-review-fit-module { background: #fcfaf7; border: 1px solid #ebdfcf; }',
    '.hdl-mistakes-module { background: #fbf5ee; border: 1px solid #ead7c6; }',
    '.hdl-context-module, .hdl-performance-module, .hdl-specs-module { background: #f9f5ef; border: 1px solid #e9dece; }',
    '.hdl-quick-answer p, .hdl-final-verdict p { margin: 0.8rem 0; }',
    '.hdl-quick-answer p strong { display: inline-block; min-width: 11rem; }',
    '.hdl-decision-grid { margin: 1.6rem 0 2rem; }',
    '.hdl-decision-grid ul { list-style: none; padding: 0; margin: 1rem 0 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.95rem; }',
    '.hdl-decision-grid li { margin: 0; padding: 1rem 1rem 1rem 1.05rem; border-radius: 16px; border: 1px solid #eadfce; background: #fcfaf7; box-shadow: 0 8px 24px rgba(44, 36, 23, 0.05); }',
    '.hdl-decision-grid li strong { display: block; margin-bottom: 0.35rem; }',
    '.hdl-product-reviews { margin: 2rem 0; }',
    '.hdl-product-review-card { margin: 1.3rem 0 1.6rem; padding: 1.35rem 1.35rem 1.1rem; border: 1px solid #e8dbc9; border-radius: 20px; background: #fffdf9; box-shadow: 0 12px 30px rgba(44, 36, 23, 0.06); }',
    '.hdl-product-review-card h3 { margin-top: 0; font-size: 1.45rem; }',
    '.hdl-product-review-card h4 { margin-top: 1.2rem; margin-bottom: 0.55rem; color: #2d261d; }',
    '.hdl-product-review-card ul { padding-left: 1.1rem; }',
    '.hdl-product-review-card p:first-of-type strong { color: #7b5a2f; }',
    '.hdl-table-wrap { margin: 1.35rem 0 0.85rem; overflow-x: auto; border: 1px solid #eadbc8; border-radius: 18px; background: #fffdfa; box-shadow: 0 10px 28px rgba(44, 36, 23, 0.05); }',
    '.hdl-table { width: 100%; border-collapse: collapse; min-width: 760px; }',
    '.hdl-table thead th { background: #f4ecdf; font-weight: 700; font-size: 0.95rem; }',
    '.hdl-table th, .hdl-table td { padding: 0.85rem 0.9rem; border-bottom: 1px solid #efe3d5; vertical-align: top; }',
    '.hdl-table tbody tr:nth-child(even) { background: rgba(247, 242, 235, 0.5); }',
    '.hdl-article-content h2 { text-align: center; font-weight: 700; color: #111; }',
    '.hdl-article-content h3 { text-align: left; font-weight: 700; color: #111; }',
    '.hdl-article-content p,',
    '.hdl-article-content li,',
    '.hdl-article-content td,',
    '.hdl-article-content th { text-align: left; color: #111; }',
    '.hdl-table th { font-weight: 700; }',
    '.hdl-article-content blockquote { margin: 1.5rem 0; padding: 0.9rem 1.1rem; border-left: 4px solid #b8a189; background: #f6f1ea; color: #111; }',
    '.hdl-article-content blockquote p { margin: 0; }',
    '.hdl-faq-section { margin: 2rem 0; }',
    '.hdl-faq-accordion { margin-top: 1rem; display: grid; gap: 0.85rem; }',
    '.hdl-faq-item { border: 1px solid #eadfce; border-radius: 16px; background: #fffdfa; overflow: hidden; }',
    '.hdl-faq-item summary { cursor: pointer; list-style: none; padding: 1rem 1.1rem; font-weight: 700; }',
    '.hdl-faq-item summary::-webkit-details-marker { display: none; }',
    '.hdl-faq-item[open] summary { border-bottom: 1px solid #efe3d5; background: #f8f2e9; }',
    '.hdl-faq-answer { padding: 0.95rem 1.1rem 1.1rem; }',
    '.hdl-faq-answer p:first-child { margin-top: 0; }',
    '.hdl-article-content figure.hdl-image-block { margin-left: auto; margin-right: auto; text-align: center; }',
    '.hdl-article-content figure.hdl-image-block img { display: block; margin-left: auto; margin-right: auto; }',
    '.hdl-article-content figure.hdl-image-block figcaption { text-align: center; }',
    '@media (max-width: 960px) { .hdl-toc ul, .hdl-jump-links ul { grid-template-columns: repeat(2, minmax(0, 1fr)); } }',
    '@media (max-width: 720px) { .hdl-article-content { max-width: 100%; } .hdl-quick-answer p strong { min-width: 0; display: block; margin-bottom: 0.25rem; } .hdl-product-review-card { padding: 1.1rem 1rem; } .hdl-toc ul, .hdl-jump-links ul { grid-template-columns: 1fr; } }',
    '</style>',
  ].join('\n');
}

function isHorizontalRule(line) {
  return /^(-{3,}|\*{3,}|_{3,})$/.test(line);
}

function isListItem(line) {
  return /^\s*(?:[-*+]\s+|\d+\.\s+)/.test(line);
}

function isBlockquoteLine(line) {
  return /^\s*>\s?/.test(line);
}

function consumeList(lines, startIndex) {
  const ordered = /^\s*\d+\.\s+/.test(lines[startIndex]);
  const tag = ordered ? 'ol' : 'ul';
  const items = [];
  let index = startIndex;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      break;
    }
    if (ordered && !/^\s*\d+\.\s+/.test(line)) {
      break;
    }
    if (!ordered && !/^\s*[-*+]\s+/.test(line)) {
      break;
    }
    items.push(`<li>${convertInlineMarkdown(line.replace(/^\s*(?:[-*+]|\d+\.)\s+/, ''))}</li>`);
    index += 1;
  }

  return {
    html: `<${tag}>\n${items.join('\n')}\n</${tag}>`,
    nextIndex: index,
  };
}

function consumeParagraph(lines, startIndex) {
  const parts = [];
  let index = startIndex;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      break;
    }
    if (
      isListItem(line)
      || isBlockquoteLine(line)
      || isHorizontalRule(trimmed)
      || line.match(/^(#{1,4})\s+/)
      || isTableStart(line, lines[index + 1] || '')
    ) {
      break;
    }
    parts.push(trimmed);
    index += 1;
  }

  return `<p>${convertInlineMarkdown(parts.join(' '))}</p>`;
}

function advanceParagraph(lines, startIndex) {
  let index = startIndex;
  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      return index + 1;
    }
    if (
      index !== startIndex
      && (
        isListItem(line)
        || isBlockquoteLine(line)
        || isHorizontalRule(trimmed)
        || line.match(/^(#{1,4})\s+/)
        || isTableStart(line, lines[index + 1] || '')
      )
    ) {
      return index;
    }
    index += 1;
  }
  return index;
}

function consumeBlockquote(lines, startIndex) {
  const parts = [];
  let index = startIndex;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      break;
    }
    if (!isBlockquoteLine(line)) {
      break;
    }
    parts.push(line.replace(/^\s*>\s?/, '').trim());
    index += 1;
  }

  const body = parts.join(' ').trim();
  return {
    html: `<blockquote>\n<p>${convertInlineMarkdown(body)}</p>\n</blockquote>`,
    nextIndex: index,
  };
}

function convertInlineMarkdown(text) {
  let result = escapeHtml(text);
  result = result.replace(/__INLINE_CODE_(\d+)__/g, '__INLINE_CODE_$1__');
  result = result.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  result = result.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  result = result.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  result = result.replace(/_([^_]+)_/g, '<em>$1</em>');
  result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, url) => `<a href="${escapeHtml(url)}">${label}</a>`);
  return result;
}

function isPotentialTableRow(line) {
  const trimmed = String(line || '').trim();
  return trimmed.includes('|') && trimmed !== '';
}

function isTableStart(line, nextLine) {
  return isPotentialTableRow(line) && /^\s*\|?[:\- ]+\|[:\-| ]+$/.test(String(nextLine || '').trim());
}

function parseTableRow(line) {
  const trimmed = String(line || '').trim().replace(/^\|/, '').replace(/\|$/, '');
  return trimmed.split('|').map((cell) => cell.trim());
}

function convertMarkdownTableToHtml(rows, warnings) {
  if (!rows || rows.length < 2) {
    return '';
  }

  const headerCells = parseTableRow(rows[0]);
  const separatorCells = parseTableRow(rows[1]);
  if (!separatorCells.every((cell) => /^:?-{3,}:?$/.test(cell))) {
    if (Array.isArray(warnings)) {
      warnings.push(`Skipped invalid table row: ${rows[0]}`);
    }
    return '';
  }

  const dataRows = rows.slice(2);
  const bodyRows = dataRows
    .map((row) => parseTableRow(row))
    .filter((cells) => cells.length && cells.some((cell) => cell !== ''));

  let html = '<div class="hdl-table-wrap">\n  <table class="hdl-table">\n    <thead>\n      <tr>\n';
  headerCells.forEach((cell) => {
    html += `        <th>${convertInlineMarkdown(cell)}</th>\n`;
  });
  html += '      </tr>\n    </thead>\n    <tbody>\n';

  bodyRows.forEach((cells) => {
    html += '      <tr>\n';
    cells.forEach((cell) => {
      html += `        <td>${convertInlineMarkdown(cell)}</td>\n`;
    });
    html += '      </tr>\n';
  });

  html += '    </tbody>\n  </table>\n</div>';
  return html;
}

function wrapQuickAnswerSection(html) {
  if (html.includes('class="hdl-quick-answer"')) {
    return html;
  }
  return html.replace(
    /<h2>Quick Answer<\/h2>([\s\S]*?)(?=<h2>|$)/i,
    (_match, body) => `<section class="hdl-quick-answer">\n<h2>Quick Answer</h2>${body}\n</section>\n`,
  ).trim();
}

function wrapFaqSection(html) {
  if (html.includes('class="hdl-faq-section"')) {
    return html;
  }

  return html.replace(/<h2>(FAQ|Frequently Asked Questions|Frequently asked questions)<\/h2>([\s\S]*?)(?=<h2>|$)/i, (_match, title, body) => {
    const trimmedBody = body.trim();
    if (!trimmedBody) {
      return `<section class="hdl-faq-section">\n<h2>${title}</h2>\n</section>\n`;
    }

    const items = trimmedBody
      .split(/(?=<h3>)/i)
      .map((chunk) => chunk.trim())
      .filter(Boolean)
      .map((chunk) => `<div class="hdl-faq-item">\n${chunk}\n</div>`)
      .join('\n');

    return `<section class="hdl-faq-section">\n<h2>${title}</h2>\n${items}\n</section>\n`;
  }).trim();
}

function makeWordPressRequest(method, requestPath, data, baseUrl, username, appPassword, extraHeaders = {}) {
  return new Promise((resolve, reject) => {
    const base = new URL(baseUrl);
    const client = base.protocol === 'http:' ? http : https;
    const credentials = Buffer.from(`${username}:${appPassword}`).toString('base64');
    const headers = {
      Authorization: `Basic ${credentials}`,
      'User-Agent': 'ContentMachine/1.0',
      ...extraHeaders,
    };

    if (data && method !== 'GET' && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    if (data && method !== 'GET' && !headers['Content-Length']) {
      headers['Content-Length'] = Buffer.byteLength(data);
    }

    const options = {
      protocol: base.protocol,
      hostname: base.hostname,
      port: base.port || (base.protocol === 'http:' ? 80 : 443),
      path: requestPath.startsWith('/') ? requestPath : `/${requestPath}`,
      method,
      headers,
    };

    const req = client.request(options, (res) => {
      let responseData = '';
      res.on('data', (chunk) => {
        responseData += chunk;
      });
      res.on('end', () => {
        const isJson = (res.headers['content-type'] || '').includes('application/json');
        const parsedData = responseData && isJson ? JSON.parse(responseData) : responseData || null;
        if (res.statusCode >= 400) {
          reject(new Error(`WordPress API error (${res.statusCode}): ${responseData}`));
          return;
        }
        resolve({ status: res.statusCode, data: parsedData });
      });
    });

    req.on('error', reject);
    if (data && method !== 'GET') {
      req.write(data);
    }
    req.end();
  });
}

module.exports = {
  escapeHtml,
  slugify,
  markdownToHtml,
  makeWordPressRequest,
  buildScopedStyleBlock,
};
