#!/usr/bin/env node

const assert = require('assert');
const {
  isHtmlContent,
  normalizeHtmlContent,
  renderArticleHtml,
  wrapGutenbergHtmlBlock,
} = require('./article-html-renderer');

const sourceHtml = `
<article class="best-x-for-y-post">
  <section class="money-hero">
    <h1>Best Dehumidifier for Mould Australia</h1>
    <nav class="jump-links" aria-label="Quick article navigation">
      <ul><li><a href="#quick-comparison">Quick comparison</a></li></ul>
    </nav>
    <div id="top-picks" class="top-picks-grid">
      <div class="product-card featured">
        <span class="badge">Best Overall</span>
        <h3>Ausclimate Large 35L Dehumidifier</h3>
        <a class="button cta-button" href="https://example.com/product" data-product="Ausclimate Large 35L Dehumidifier" rel="nofollow sponsored" target="_blank">Check latest price</a>
      </div>
    </div>
  </section>
  <section id="quick-comparison" class="comparison-section">
    <h2>Quick comparison</h2>
    <div class="table-wrap">
      <table class="comparison-table">
        <thead><tr><th>Model</th><th>Capacity</th></tr></thead>
        <tbody><tr><td>Ausclimate Large 35L</td><td>35 L/day</td></tr></tbody>
      </table>
    </div>
  </section>
  <section id="faq" class="hdl-faq-section">
    <h2>Frequently asked questions</h2>
    <h3>What humidity should I aim for?</h3>
    <p>A practical target is around 45 to 55 percent.</p>
    <h3>Do dehumidifiers help with mould?</h3>
    <p>They help reduce the moisture mould needs to grow.</p>
  </section>
</article>
</section>
</div>
`;

assert.equal(isHtmlContent(sourceHtml), true);

const normalized = normalizeHtmlContent(sourceHtml);
assert.match(normalized, /<table class="hdl-table">/);
assert.match(normalized, /<div class="hdl-table-wrap">/);
assert.match(normalized, /<nav class="hdl-jump-links"/);
assert.doesNotMatch(normalized, /<\/section>\s*<\/div>\s*$/);

const rendered = renderArticleHtml(sourceHtml, {
  post_type: 'best_x_for_y',
  wordpressBlocks: true,
});

assert.match(rendered, /^<!-- wp:html -->/);
assert.match(rendered, /<!-- \/wp:html -->$/);
assert.match(rendered, /<table class="hdl-table">/);
assert.match(rendered, /<div class="product-card featured">/);
assert.match(rendered, /data-product="Ausclimate Large 35L Dehumidifier"/);
assert.match(rendered, /rel="nofollow sponsored"/);
assert.match(rendered, /target="_blank"/);
assert.match(rendered, /<div class="hdl-faq-accordion">/);
assert.match(rendered, /<details class="hdl-faq-item" open>/);
assert.doesNotMatch(rendered, /<p>\s*<article/);

const alreadyWrapped = wrapGutenbergHtmlBlock(rendered);
assert.equal(alreadyWrapped, rendered);

console.log('WordPress HTML renderer tests passed.');
