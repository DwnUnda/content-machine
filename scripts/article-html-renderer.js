const { buildScopedStyleBlock, markdownToHtml, escapeHtml, stripFirstHeadingTag } = require('./wordpress-upload-utils');

const RENDER_PROFILES = {
  informational_blog: {
    wrapMethodology: false,
    sectionWrappers: [],
    decisionHeadings: [],
    productReviewHeadings: [],
    finalVerdictHeadings: ['Final thoughts', 'Conclusion'],
  },
  money_post: {
    wrapMethodology: true,
    sectionWrappers: [
      { headings: ['Quick comparison'], className: 'hdl-comparison-module' },
      { headings: ['How to choose'], className: 'hdl-buyer-guide' },
      { headings: ['Common mistakes to avoid'], className: 'hdl-mistakes-module' },
    ],
    decisionHeadings: ['Which one should you buy\\?', 'Which one suits your situation\\?'],
    productReviewHeadings: ['Recommended .*full reviews', 'Our top picks', 'Best .* reviewed'],
    finalVerdictHeadings: ['Final recommendation', 'Final thoughts'],
    jumpLinkTargets: [
      { label: 'Top picks', id: 'top-picks' },
      { label: 'Quick comparison', headings: ['Quick comparison'] },
      { label: 'Full reviews', headings: ['Recommended .*full reviews', 'Our top picks', 'Best .* reviewed'] },
      { label: 'How to choose', headings: ['How to choose'] },
      { label: 'FAQ', headings: ['Frequently asked questions', 'FAQ'] },
    ],
  },
  single_product_review: {
    wrapMethodology: false,
    sectionWrappers: [
      { headings: ['Key specifications'], className: 'hdl-specs-module' },
      { headings: ['Real-world performance'], className: 'hdl-performance-module' },
      { headings: ['How it compares to alternatives'], className: 'hdl-comparison-module' },
      { headings: ['Who should buy this', 'Who should look elsewhere'], className: 'hdl-review-fit-module' },
    ],
    decisionHeadings: [],
    productReviewHeadings: [],
    finalVerdictHeadings: ['Final verdict', 'Bottom line', 'Final recommendation'],
  },
  product_comparison: {
    wrapMethodology: true,
    sectionWrappers: [
      { headings: ['Head-to-head comparison'], className: 'hdl-comparison-module' },
      { headings: ['How to choose between them'], className: 'hdl-buyer-guide' },
    ],
    decisionHeadings: ['Which one should you buy\\?', 'Winner by use case', 'Which one suits your situation\\?'],
    productReviewHeadings: ['Detailed comparison', 'Product-by-product comparison', 'Recommended .*full reviews'],
    finalVerdictHeadings: ['Final recommendation', 'Final verdict'],
    jumpLinkTargets: [],
  },
  best_x_for_y: {
    wrapMethodology: true,
    sectionWrappers: [
      { headings: ['Quick comparison'], className: 'hdl-comparison-module' },
      { headings: ['Why the right product matters for .*'], className: 'hdl-context-module' },
      { headings: ['How to choose for .*', 'How to choose'], className: 'hdl-buyer-guide' },
      { headings: ['Common mistakes when buying for .*', 'Common mistakes to avoid'], className: 'hdl-mistakes-module' },
    ],
    decisionHeadings: ['Which one suits your situation\\?', 'Which one should you buy\\?'],
    productReviewHeadings: ['Recommended .*full reviews', 'Best .* reviewed'],
    finalVerdictHeadings: ['Final recommendation', 'Final thoughts'],
    jumpLinkTargets: [
      { label: 'Top picks', id: 'top-picks' },
      { label: 'Use-case fit', headings: ['Which one suits your situation\\?', 'Which one should you buy\\?'] },
      { label: 'Quick comparison', headings: ['Quick comparison'] },
      { label: 'Full reviews', headings: ['Recommended .*full reviews', 'Best .* reviewed'] },
      { label: 'FAQ', headings: ['Frequently asked questions', 'FAQ'] },
    ],
  },
};

function getRenderProfile(postType) {
  return RENDER_PROFILES[postType] || RENDER_PROFILES.informational_blog;
}

const MODULE_CLASS_MAP = {
  top_picks: 'hdl-top-picks',
  jump_links: 'hdl-jump-links',
  methodology: 'hdl-methodology',
  decision_grid: 'hdl-decision-grid',
  comparison: 'hdl-comparison-module',
  buyer_guide: 'hdl-buyer-guide',
  mistakes: 'hdl-mistakes-module',
  context: 'hdl-context-module',
  performance: 'hdl-performance-module',
  specs: 'hdl-specs-module',
  review_fit: 'hdl-review-fit-module',
  final_verdict: 'hdl-final-verdict',
};

const SECTION_END_BOUNDARY = '(?=<h2\\b|</div>\\s*$|$)';

function isHtmlContent(content) {
  const text = String(content || '').trim();
  return (
    /^\s*<article\b/i.test(text)
    || /class=(["'])(?:[^"']*\s)?(?:money-post|best-x-for-y-post|single-product-review|product-comparison-post)(?:\s[^"']*)?\1/i.test(text)
  );
}

function stripScopedStyleBlock(html) {
  return String(html || '').replace(/^\s*<style>[\s\S]*?<\/style>\s*/i, '').trim();
}

function normalizeGeneratedHtmlClasses(html) {
  return String(html || '')
    .replace(/\bclass=(["'])jump-links\1/gi, 'class="hdl-jump-links"')
    .replace(/\bclass=(["'])table-wrap\1/gi, 'class="hdl-table-wrap"')
    .replace(/\bclass=(["'])comparison-table\1/gi, 'class="hdl-table"')
    .replace(/\bclass=(["'])decision-grid\1/gi, 'class="hdl-decision-grid"')
    .replace(/\bclass=(["'])methodology-box\1/gi, 'class="hdl-methodology"')
    .replace(/\bclass=(["'])buyer-guide\1/gi, 'class="hdl-buyer-guide"')
    .replace(/\bclass=(["'])mistakes-section\1/gi, 'class="hdl-mistakes-module"')
    .replace(/\bclass=(["'])problem-context-section\1/gi, 'class="hdl-context-module"')
    .replace(/\bclass=(["'])faq-section\1/gi, 'class="hdl-faq-section"')
    .replace(/\bclass=(["'])final-verdict\1/gi, 'class="hdl-final-verdict"');
}

function removeUnmatchedClosingContainerTags(html) {
  const containerTags = new Set(['article', 'aside', 'div', 'figure', 'nav', 'section']);
  const stack = [];
  const tagRegex = /<\/?([a-z][a-z0-9-]*)(?:\s[^>]*)?>/gi;
  let output = '';
  let lastIndex = 0;
  let match;

  while ((match = tagRegex.exec(html)) !== null) {
    const fullTag = match[0];
    const tagName = match[1].toLowerCase();
    if (!containerTags.has(tagName)) {
      continue;
    }

    output += html.slice(lastIndex, match.index);
    lastIndex = match.index + fullTag.length;

    const isClosing = fullTag.startsWith('</');
    const isSelfClosing = /\/>$/.test(fullTag);
    if (!isClosing && !isSelfClosing) {
      stack.push(tagName);
      output += fullTag;
      continue;
    }

    if (!isClosing) {
      output += fullTag;
      continue;
    }

    const matchingIndex = stack.lastIndexOf(tagName);
    if (matchingIndex === -1) {
      continue;
    }
    stack.splice(matchingIndex, 1);
    output += fullTag;
  }

  return output + html.slice(lastIndex);
}

function normalizeHtmlContent(html) {
  return enhanceFaqAccordions(
    removeUnmatchedClosingContainerTags(normalizeGeneratedHtmlClasses(stripScopedStyleBlock(html))),
  ).trim();
}

function wrapGutenbergHtmlBlock(html) {
  const body = String(html || '').trim();
  if (!body || /<!--\s+wp:html\s+-->/.test(body)) {
    return body;
  }
  return `<!-- wp:html -->\n${body}\n<!-- /wp:html -->`;
}

function slugifyHeadingId(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/&amp;/g, 'and')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    || 'section';
}

function buildTableOfContentsHtml(items) {
  if (!Array.isArray(items) || !items.length) {
    return '';
  }
  const links = items.map((item) => `    <li><a href="#${escapeHtml(item.id)}">${escapeHtml(item.text)}</a></li>`).join('\n');
  return [
    '<nav class="hdl-toc" aria-label="Table of contents">',
    '  <h2>Table of Contents</h2>',
    '  <ul>',
    links,
    '  </ul>',
    '</nav>',
  ].join('\n');
}

function stripTags(value) {
  return String(value || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function stripLeadingRank(text) {
  return String(text || '').replace(/^\s*\d+\.\s*/, '').trim();
}

function findComparisonSectionCloseIndex(html) {
  const patterns = [
    '<section class="comparison-section"',
    '<section class="hdl-comparison-module"',
  ];
  for (const pattern of patterns) {
    const sectionIndex = html.indexOf(pattern);
    if (sectionIndex !== -1) {
      const closeIndex = html.indexOf('</section>', sectionIndex);
      if (closeIndex !== -1) {
        return closeIndex + '</section>'.length;
      }
    }
  }
  return -1;
}

function addTableOfContents(html, postType = 'informational_blog') {
  const h2Regex = /<h2([^>]*)>([\s\S]*?)<\/h2>/gi;
  const items = [];
  const seenIds = new Set();
  let firstHeadingIndex = -1;
  const updated = html.replace(h2Regex, (match, attrs, inner, offset) => {
    const text = inner.replace(/<[^>]+>/g, '').trim();
    if (!text) {
      return match;
    }
    if (firstHeadingIndex === -1) {
      firstHeadingIndex = offset;
    }
    const idMatch = attrs.match(/\sid=(["'])(.*?)\1/i);
    let id = idMatch ? idMatch[2] : slugifyHeadingId(text);
    let suffix = 2;
    while (seenIds.has(id)) {
      id = `${slugifyHeadingId(text)}-${suffix}`;
      suffix += 1;
    }
    seenIds.add(id);
    items.push({ id, text });
    if (idMatch) {
      return match;
    }
    return `<h2${attrs} id="${id}">${inner}</h2>`;
  });

  if (!items.length || firstHeadingIndex === -1 || updated.includes('class="hdl-toc"')) {
    return updated;
  }

  let insertIndex = firstHeadingIndex;
  if (postType === 'money_post' || postType === 'best_x_for_y') {
    const comparisonCloseIndex = findComparisonSectionCloseIndex(updated);
    if (comparisonCloseIndex !== -1) {
      insertIndex = comparisonCloseIndex;
    }
  }
  const quickAnswerIndex = updated.lastIndexOf('<section class="hdl-quick-answer">', firstHeadingIndex);
  if (quickAnswerIndex !== -1) {
    const quickAnswerCloseBeforeHeading = updated.indexOf('</section>', quickAnswerIndex);
    if (quickAnswerCloseBeforeHeading === -1 || quickAnswerCloseBeforeHeading >= firstHeadingIndex) {
      insertIndex = quickAnswerIndex;
    }
  }

  const toc = buildTableOfContentsHtml(items);
  return `${updated.slice(0, insertIndex)}${toc}\n${updated.slice(insertIndex)}`;
}

function wrapSectionByHeading(html, headingPattern, className) {
  const regex = new RegExp(`<h2([^>]*)>(${headingPattern})<\\/h2>([\\s\\S]*?)${SECTION_END_BOUNDARY}`, 'i');
  return html.replace(regex, (_match, attrs, title, body) => (
    `<section class="${className}">\n<h2${attrs}>${title}</h2>${body}\n</section>\n`
  ));
}

function wrapSectionsByProfile(html, sectionWrappers) {
  let output = html;
  sectionWrappers.forEach((wrapper) => {
    const pattern = wrapper.headings.join('|');
    output = wrapSectionByHeading(output, pattern, wrapper.className);
  });
  return output;
}

function escapeRegex(text) {
  return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeContentModules(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({
      module_type: String(item.module_type || item.type || '').trim(),
      heading: String(item.heading || '').trim(),
    }))
    .filter((item) => item.module_type && item.heading);
}

function injectProductReviewIds(html) {
  let output = html;
  const seenIds = new Set();

  output = output.replace(/<h2([^>]*)>([\s\S]*?)<\/h2>/gi, (match, attrs, inner) => {
    if (/\sid=(["']).*?\1/i.test(attrs)) {
      return match;
    }
    const headingText = stripTags(inner);
    if (!/\d+\./.test(headingText) && !/best/i.test(headingText)) {
      return match;
    }
    const productName = stripLeadingRank(headingText.split('—')[0]);
    if (!productName) {
      return match;
    }
    let id = `${slugifyHeadingId(productName)}-review`;
    let suffix = 2;
    while (seenIds.has(id)) {
      id = `${slugifyHeadingId(productName)}-review-${suffix}`;
      suffix += 1;
    }
    seenIds.add(id);
    return `<h2${attrs} id="${id}">${inner}</h2>`;
  });

  output = output.replace(/<article class="hdl-product-review-card"([^>]*)>([\s\S]*?)<\/article>/gi, (match, attrs, body) => {
    if (/\sid=(["']).*?\1/i.test(attrs)) {
      return match;
    }
    const headingMatch = body.match(/<h[23][^>]*>([\s\S]*?)<\/h[23]>/i);
    if (!headingMatch) {
      return match;
    }
    const productName = stripLeadingRank(stripTags(headingMatch[1]).split('—')[0]);
    if (!productName) {
      return match;
    }
    let id = `${slugifyHeadingId(productName)}-review`;
    let suffix = 2;
    while (seenIds.has(id)) {
      id = `${slugifyHeadingId(productName)}-review-${suffix}`;
      suffix += 1;
    }
    seenIds.add(id);
    return `<article class="hdl-product-review-card"${attrs} id="${id}">${body}</article>`;
  });

  return output;
}

function ensureTopPickImagesAndReviewLinks(cardHtml) {
  const headingMatch = cardHtml.match(/<h3[^>]*>([\s\S]*?)<\/h3>/i);
  const productName = stripTags(headingMatch ? headingMatch[1] : 'Product');
  const reviewId = `${slugifyHeadingId(productName || 'product')}-review`;

  let output = cardHtml;
  if (!/class="product-image-wrap"/i.test(output)) {
    const placeholder = [
      '<figure class="product-image-wrap">',
      `  <p class="product-image-placeholder" aria-hidden="true">${escapeHtml(productName || 'Product')}</p>`,
      '</figure>',
    ].join('\n');
    output = output.replace(/(<span class="badge">[\s\S]*?<\/span>)/i, `$1\n${placeholder}`);
  } else {
    output = output.replace(/<figure class="product-image-wrap">([\s\S]*?)<\/figure>/i, (figureMatch, figureBody) => {
      if (/<img\b/i.test(figureBody)) {
        return figureMatch;
      }
      return [
        '<figure class="product-image-wrap">',
        `  <p class="product-image-placeholder" aria-hidden="true">${escapeHtml(productName || 'Product')}</p>`,
        '</figure>',
      ].join('\n');
    });
  }

  if (!/class="read-review-link"/i.test(output)) {
    output = output.replace(
      /(<a class="button cta-button"[\s\S]*?<\/a>)/i,
      `$1\n<a class="read-review-link" href="#${escapeHtml(reviewId)}">Read review</a>`,
    );
  } else {
    output = output.replace(/<a class="read-review-link"[^>]*href=(["']).*?\1/i, `<a class="read-review-link" href="#${escapeHtml(reviewId)}"`);
  }
  return output;
}

function enhanceTopPicks(html) {
  let output = html.replace(/<div class="top-picks-grid"(?![^>]*\sid=)/i, '<div class="top-picks-grid" id="top-picks"');
  output = output.replace(/<div class="product-card featured">([\s\S]*?)<\/div>/gi, (match, body) => {
    return `<div class="product-card featured">\n${ensureTopPickImagesAndReviewLinks(body.trim())}\n</div>`;
  });
  return output;
}

function collectHeadingTargets(html) {
  const targets = [];
  const h2Regex = /<h2([^>]*)>([\s\S]*?)<\/h2>/gi;
  let match = h2Regex.exec(html);
  while (match) {
    const attrs = match[1] || '';
    const text = stripTags(match[2]);
    const idMatch = attrs.match(/\sid=(["'])(.*?)\1/i);
    if (text && idMatch) {
      targets.push({ id: idMatch[2], text });
    }
    match = h2Regex.exec(html);
  }
  return targets;
}

function resolveJumpLinkTarget(profileTarget, headingTargets) {
  if (profileTarget.id) {
    return profileTarget.id;
  }
  const patterns = (profileTarget.headings || []).map((pattern) => new RegExp(`^${pattern}$`, 'i'));
  const match = headingTargets.find((target) => patterns.some((pattern) => pattern.test(target.text)));
  return match ? match.id : null;
}

function addJumpLinks(html, postType = 'informational_blog') {
  const profile = getRenderProfile(postType);
  const jumpTargets = Array.isArray(profile.jumpLinkTargets) ? profile.jumpLinkTargets : [];
  if (!jumpTargets.length || html.includes('class="hdl-jump-links"')) {
    return html;
  }

  const headingTargets = collectHeadingTargets(html);
  const items = jumpTargets
    .map((target) => ({ label: target.label, id: resolveJumpLinkTarget(target, headingTargets) }))
    .filter((item) => item.id);
  if (items.length < 3) {
    return html;
  }

  const links = items.map((item) => `    <a href="#${escapeHtml(item.id)}">${escapeHtml(item.label)}</a>`).join('\n');
  const navHtml = [
    '<nav class="hdl-jump-links" aria-label="Quick article navigation">',
    links,
    '</nav>',
  ].join('\n');

  if (postType === 'money_post' || postType === 'best_x_for_y') {
    const comparisonCloseIndex = findComparisonSectionCloseIndex(html);
    if (comparisonCloseIndex !== -1) {
      return `${html.slice(0, comparisonCloseIndex)}\n${navHtml}\n${html.slice(comparisonCloseIndex)}`;
    }
  }

  const tocIndex = html.indexOf('<nav class="hdl-toc"');
  if (tocIndex !== -1) {
    const tocClose = html.indexOf('</nav>', tocIndex);
    if (tocClose !== -1) {
      return `${html.slice(0, tocClose + 6)}\n${navHtml}\n${html.slice(tocClose + 6)}`;
    }
  }

  const heroClose = html.indexOf('</section>');
  if (heroClose !== -1) {
    return `${html.slice(0, heroClose)}\n${navHtml}\n${html.slice(heroClose)}`;
  }
  return `${navHtml}\n${html}`;
}

function applyExplicitContentModules(html, contentModules) {
  let output = html;
  normalizeContentModules(contentModules).forEach((module) => {
    const className = MODULE_CLASS_MAP[module.module_type];
    if (!className || output.includes(`class="${className}"`)) {
      return;
    }
    if (module.module_type === 'top_picks') {
      output = enhanceTopPicks(output);
      return;
    }
    if (module.module_type === 'jump_links') {
      return;
    }
    if (module.module_type === 'decision_grid') {
      const regex = new RegExp(`<h2([^>]*)>(${escapeRegex(module.heading)})<\\/h2>\\s*(<ul>[\\s\\S]*?<\\/ul>)`, 'i');
      output = output.replace(regex, (_match, attrs, title, list) => `<section class="${className}">\n<h2${attrs}>${title}</h2>\n${list}\n</section>\n`);
      return;
    }
    if (module.module_type === 'product_reviews') {
      const regex = new RegExp(`<h2([^>]*)>(${escapeRegex(module.heading)})<\\/h2>([\\s\\S]*?)${SECTION_END_BOUNDARY}`, 'i');
      output = output.replace(regex, (_match, attrs, title, body) => {
        const cards = body
          .split(/(?=<h3\b)/i)
          .map((chunk) => chunk.trim())
          .filter(Boolean)
          .map((chunk) => `<article class="hdl-product-review-card">\n${chunk}\n</article>`)
          .join('\n');
        return `<section class="hdl-product-reviews">\n<h2${attrs}>${title}</h2>\n${cards}\n</section>\n`;
      });
      return;
    }
    output = wrapSectionByHeading(output, escapeRegex(module.heading), className);
  });
  return output;
}

function enhanceDecisionGrid(html, headingPatterns) {
  if (!headingPatterns.length) {
    return html;
  }
  const alternation = headingPatterns.join('|');
  const regex = new RegExp(`<h2([^>]*)>(${alternation})<\\/h2>\\s*(<ul>[\\s\\S]*?<\\/ul>)`, 'i');
  return html.replace(regex, (_match, attrs, title, list) => `<section class="hdl-decision-grid">\n<h2${attrs}>${title}</h2>\n${list}\n</section>\n`);
}

function enhanceProductReviewSection(html, headingPatterns) {
  if (!headingPatterns.length) {
    return html;
  }
  const alternation = headingPatterns.join('|');
  const regex = new RegExp(`<h2([^>]*)>(${alternation})<\\/h2>([\\s\\S]*?)${SECTION_END_BOUNDARY}`, 'i');
  return html.replace(
    regex,
    (_match, attrs, title, body) => {
      const cards = body
        .split(/(?=<h3\b)/i)
        .map((chunk) => chunk.trim())
        .filter(Boolean)
        .map((chunk) => `<article class="hdl-product-review-card">\n${chunk}\n</article>`)
        .join('\n');
      return `<section class="hdl-product-reviews">\n<h2${attrs}>${title}</h2>\n${cards}\n</section>\n`;
    },
  );
}

function enhanceFaqAccordions(html) {
  return html.replace(
    /<section\b([^>]*)>\s*<h2([^>]*)>([\s\S]*?)<\/h2>([\s\S]*?)<\/section>/gi,
    (match, sectionAttrs, titleAttrs, title, body) => {
      if (!/\bclass=(['"])[^'"]*\bhdl-faq-section\b[^'"]*\1/i.test(sectionAttrs)) {
        return match;
      }

      const source = body.trim();
      if (!source) {
        return `<section${sectionAttrs}>\n<h2${titleAttrs}>${title}</h2>\n</section>`;
      }

      const items = [];
      if (/<div class="hdl-faq-item">/i.test(source)) {
        const chunks = source.match(/<div class="hdl-faq-item">[\s\S]*?<\/div>/gi) || [];
        chunks.forEach((chunk) => {
          const questionMatch = chunk.match(/<(?:h3|p)>\s*(?:<strong>)?([\s\S]*?)(?:<\/strong>)?\s*<\/(?:h3|p)>/i);
          const answer = chunk
            .replace(/<div class="hdl-faq-item">/i, '')
            .replace(/<\/div>$/i, '')
            .replace(/<(?:h3|p)>\s*(?:<strong>)?[\s\S]*?(?:<\/strong>)?\s*<\/(?:h3|p)>/i, '')
            .trim();
          if (questionMatch && answer) {
            items.push({ question: questionMatch[1].replace(/<[^>]+>/g, '').trim(), answer });
          }
        });
      } else {
        const blocks = source.split(/(?=<h3\b|<p><strong>)/i).map((chunk) => chunk.trim()).filter(Boolean);
        blocks.forEach((chunk) => {
          let question = '';
          let answer = '';
          const h3Match = chunk.match(/^<h3[^>]*>([\s\S]*?)<\/h3>([\s\S]*)$/i);
          const strongMatch = chunk.match(/^<p><strong>([\s\S]*?)<\/strong><\/p>([\s\S]*)$/i);
          if (h3Match) {
            question = h3Match[1].replace(/<[^>]+>/g, '').trim();
            answer = h3Match[2].trim();
          } else if (strongMatch) {
            question = strongMatch[1].replace(/<[^>]+>/g, '').trim();
            answer = strongMatch[2].trim();
          }
          if (question && answer) {
            items.push({ question, answer });
          }
        });
      }

      const accordion = items.map((item, index) => [
        `<details class="hdl-faq-item"${index === 0 ? ' open' : ''}>`,
        `  <summary>${escapeHtml(item.question)}</summary>`,
        `  <div class="hdl-faq-answer">\n${item.answer}\n  </div>`,
        '</details>',
      ].join('\n')).join('\n');

      return `<section${sectionAttrs}>\n<h2${titleAttrs}>${title}</h2>\n<div class="hdl-faq-accordion">\n${accordion}\n</div>\n</section>`;
    },
  );
}

function enhanceArticleHtml(html, postType = 'informational_blog', contentModules = []) {
  const profile = getRenderProfile(postType);
  let output = html;
  output = output.replace(/<nav class="jump-links"[\s\S]*?<\/nav>/i, '');
  output = applyExplicitContentModules(output, contentModules);
  output = enhanceTopPicks(output);
  output = wrapSectionsByProfile(output, profile.sectionWrappers || []);
  if (profile.wrapMethodology) {
    output = wrapSectionByHeading(output, 'How we chose these products', 'hdl-methodology');
  }
  output = wrapSectionByHeading(output, profile.finalVerdictHeadings.join('|'), 'hdl-final-verdict');
  output = enhanceDecisionGrid(output, profile.decisionHeadings);
  output = enhanceProductReviewSection(output, profile.productReviewHeadings);
  output = injectProductReviewIds(output);
  output = enhanceFaqAccordions(output);
  return output;
}

function renderArticleHtml(content, options = {}) {
  const postType = options.post_type || 'informational_blog';
  const contentModules = options.content_modules || [];
  const wordpressBlocks = Boolean(options.wordpressBlocks);
  const body = String(content || '');
  if (isHtmlContent(body)) {
    const html = `${buildScopedStyleBlock()}\n<div class="hdl-article-content">\n${stripFirstHeadingTag(normalizeHtmlContent(body))}\n</div>`;
    return wordpressBlocks ? wrapGutenbergHtmlBlock(html) : html;
  }
  const html = addJumpLinks(
    addTableOfContents(enhanceArticleHtml(markdownToHtml(body, {
      stripFirstH1: true,
      stripHorizontalRules: true,
      wrapContainer: true,
      wrapSpecialSections: true,
      warnings: [],
    }), postType, contentModules), postType),
    postType,
  );
  return wordpressBlocks ? wrapGutenbergHtmlBlock(html) : html;
}

module.exports = {
  addTableOfContents,
  addJumpLinks,
  enhanceArticleHtml,
  getRenderProfile,
  isHtmlContent,
  normalizeHtmlContent,
  renderArticleHtml,
  wrapGutenbergHtmlBlock,
};
