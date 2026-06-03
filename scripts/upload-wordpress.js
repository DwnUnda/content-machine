#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { escapeHtml, makeWordPressRequest, slugify } = require('./wordpress-upload-utils');
const { isHtmlContent, renderArticleHtml } = require('./article-html-renderer');

function loadEnv() {
  const envPath = path.join(__dirname, '..', '.env');
  const fileEnv = {};

  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const match = trimmed.match(/^([^=]+)=(.*)$/);
      if (!match) continue;
      fileEnv[match[1].trim()] = stripWrappingQuotes(match[2].trim());
    }
  }

  return {
    ...fileEnv,
    ...Object.fromEntries(Object.entries(process.env).map(([key, value]) => [key, stripWrappingQuotes(value)])),
  };
}

function stripWrappingQuotes(value) {
  const text = String(value ?? '');
  if ((text.startsWith('"') && text.endsWith('"')) || (text.startsWith("'") && text.endsWith("'"))) {
    return text.slice(1, -1);
  }
  return text;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJson(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf8');
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function fileExists(filePath) {
  return Boolean(filePath) && fs.existsSync(filePath);
}

function extractH1(markdown) {
  const match = String(markdown || '').match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : null;
}

function normalizeText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/&[a-z#0-9]+;/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function wordCount(text) {
  return String(text || '').trim().split(/\s+/).filter(Boolean).length;
}

function extractMarkdownHeadings(markdown) {
  return String(markdown || '')
    .split('\n')
    .map((line) => line.match(/^(##|###)\s+(.+)$/))
    .filter(Boolean)
    .map((match) => ({ level: match[1].length, text: match[2].trim() }));
}

/**
 * Extract h2/h3 headings from HTML content (for visual asset placement).
 * Falls back to Markdown heading extraction for non-HTML content.
 */
function extractHeadings(content) {
  const text = String(content || '');
  if (!isHtmlContent(text)) {
    return extractMarkdownHeadings(text);
  }
  const headings = [];
  const regex = /<h([23])[^>]*>([\s\S]*?)<\/h\1>/gi;
  let match;
  while ((match = regex.exec(text)) !== null) {
    const headingText = match[2].replace(/<[^>]+>/g, '').trim();
    if (headingText) {
      headings.push({ level: parseInt(match[1], 10), text: headingText });
    }
  }
  return headings;
}

function resolveHeadingMatch(headings, requestedHeading, visualType) {
  if (!headings.length) {
    return '';
  }

  const target = normalizeText(requestedHeading);
  if (target) {
    const exact = headings.find((heading) => normalizeText(heading.text) === target);
    if (exact) {
      return exact.text;
    }

    const targetWords = new Set(target.split(' ').filter((word) => word.length > 2));
    let bestScore = 0;
    let bestHeading = null;
    for (const heading of headings) {
      const headingWords = normalizeText(heading.text).split(' ').filter((word) => word.length > 2);
      const score = headingWords.reduce((sum, word) => sum + (targetWords.has(word) ? 1 : 0), 0);
      if (score > bestScore) {
        bestScore = score;
        bestHeading = heading;
      }
    }
    if (bestHeading && bestScore > 0) {
      return bestHeading.text;
    }
  }

  const preference = visualType === 'chart_or_infographic'
    ? /cost|compare|comparison|running|energy|electricity|buying/i
    : /context|compare|buying|dehumidifier|air purifier|recommendation/i;
  const preferredHeading = headings.find((heading) => preference.test(heading.text));
  return preferredHeading ? preferredHeading.text : headings[0].text;
}

function buildVisualContext(article) {
  return {
    title: article.seo_title || extractH1(article.draft_markdown) || article.slug || 'Article',
    slug: article.slug || 'article',
    post_type: article.post_type || 'informational_blog',
    excerpt: article.excerpt || '',
    meta_description: article.meta_description || '',
    markdown: article.draft_markdown || '',
    headings: extractHeadings(article.draft_markdown || '').map((heading) => heading.text),
    word_count: wordCount(article.draft_markdown || ''),
    // Primary/focus keyword for natural alt-text inclusion (never invented).
    focus_keyword: resolvePrimaryKeyword(article),
  };
}

const VISUAL_POLICIES = {
  informational_blog: {
    realistic_images: 1,
    chart_or_infographic: 0,
    min_word_count_for_infographic: 1600,
    realistic_heading_hints: [
      'Practical setup',
      'How it works',
      'What it looks like in a home',
    ],
    infographic_heading_hints: [
      'Checklist',
      'Decision table',
      'Running cost',
    ],
  },
  money_post: {
    realistic_images: 2,
    chart_or_infographic: 1,
    min_word_count_for_infographic: 1400,
    realistic_heading_hints: [
      'Which one should you buy',
      'How to choose',
      'What this looks like in a home',
    ],
    infographic_heading_hints: [
      'Quick comparison',
      'Running cost',
      'Decision table',
    ],
  },
  single_product_review: {
    realistic_images: 2,
    chart_or_infographic: 0,
    min_word_count_for_infographic: 2200,
    realistic_heading_hints: [
      'Who should buy it',
      'How it fits into a room',
      'Setup',
    ],
    infographic_heading_hints: [
      'Key specs',
      'Performance',
    ],
  },
  product_comparison: {
    realistic_images: 1,
    chart_or_infographic: 1,
    min_word_count_for_infographic: 1300,
    realistic_heading_hints: [
      'Winner by use case',
      'Which one should you buy',
      'Best for',
    ],
    infographic_heading_hints: [
      'Quick comparison',
      'Detailed comparison',
      'Running cost',
    ],
  },
  best_x_for_y: {
    realistic_images: 2,
    chart_or_infographic: 1,
    min_word_count_for_infographic: 1400,
    realistic_heading_hints: [
      'Which one suits your situation',
      'How to choose',
      'What this looks like in a home',
    ],
    infographic_heading_hints: [
      'Quick comparison',
      'Running cost',
      'Decision table',
    ],
  },
};

function getVisualPolicy(postType, wordCount = 0) {
  const base = VISUAL_POLICIES[postType] || VISUAL_POLICIES.informational_blog;
  return {
    ...base,
    chart_or_infographic: wordCount >= base.min_word_count_for_infographic ? base.chart_or_infographic : 0,
  };
}

/**
 * Ensure the featured image alt text naturally includes the primary keyword.
 * Keeps content-image alts varied (we do NOT force the keyword into every alt).
 * If the existing alt already contains the keyword, it is left untouched.
 */
function ensureKeywordInAltText(altText, focusKeyword, context) {
  const alt = String(altText || '').trim();
  const keyword = String(focusKeyword || '').trim();
  if (!keyword) {
    return alt || context.title;
  }
  if (alt && alt.toLowerCase().includes(keyword.toLowerCase())) {
    return alt;
  }
  if (!alt) {
    return keyword;
  }
  // Append the keyword as a natural suffix rather than overwriting the description.
  return `${alt} — ${keyword}`;
}

/**
 * Resolve the article's primary/focus keyword for Rank Math.
 * Falls back to the SEO title or H1 so we never send an empty focus keyword,
 * but never invents an unrelated keyword.
 */
function resolvePrimaryKeyword(article) {
  const candidate = String(
    article.primary_keyword
    || article.focus_keyword
    || article.seo_title
    || extractH1(article.draft_markdown)
    || '',
  ).trim();
  // Rank Math expects a plain phrase, not a question-marked title.
  return candidate.replace(/[?!.]+$/g, '').trim();
}

/**
 * Inspect the generated article HTML for external and internal links.
 * Returns counts plus warning/suggestion notes. Never inserts links itself.
 */
function analyseLinks(html, baseUrl) {
  const result = { external: 0, internal: 0, warnings: [] };
  let host = '';
  try {
    host = new URL(baseUrl).hostname.replace(/^www\./, '');
  } catch (_error) {
    host = '';
  }

  const linkRegex = /<a\s[^>]*href=["']([^"']+)["'][^>]*>/gi;
  let match;
  while ((match = linkRegex.exec(html)) !== null) {
    const href = match[1].trim();
    if (/^https?:\/\//i.test(href)) {
      const linkHost = (() => {
        try {
          return new URL(href).hostname.replace(/^www\./, '');
        } catch (_error) {
          return '';
        }
      })();
      if (host && linkHost && linkHost.endsWith(host)) {
        result.internal += 1;
      } else {
        result.external += 1;
      }
    } else if (href.startsWith('/')) {
      // Root-relative link on the same site.
      result.internal += 1;
    }
    // Placeholder "#" links are intentionally ignored (not counted as real links).
  }

  if (result.external === 0) {
    result.warnings.push(
      'No external authority link found. Consider adding one relevant, real source '
      + '(e.g. an Australian government health/housing page, a state tenancy authority, '
      + 'energy/electricity guidance, or a manufacturer support page). Do not add fake or low-quality links.',
    );
  }
  if (result.internal === 0) {
    result.warnings.push(
      'No internal link found. If you have a related Home Dry Lab article, consider linking to it. '
      + '(Warning only — not a blocker, and do not add placeholder "#" links.)',
    );
  }

  return result;
}

function buildFeaturedPrompt(context) {
  return [
    `Create a realistic 16:9 featured image for an Australian home advice article titled "${context.title}".`,
    'Show a clean, trustworthy domestic interior relevant to the article topic.',
    'No text, no labels, no logos, no brand names, no watermark.',
    'Avoid generic stock-photo staging and avoid excessive or gross mould.',
    'Do not include people unless the scene genuinely requires them.',
  ].join(' ');
}

function buildSupportingPrompt(context, heading) {
  const sectionText = heading ? `It should support the section "${heading}".` : 'It should support the article body.';
  return [
    `Create a realistic supporting image for an Australian home advice article titled "${context.title}".`,
    sectionText,
    'Use a grounded residential scene with practical detail.',
    'No text, no labels, no logos, no brand names, no watermark.',
    'Do not include people unless required by the scene.',
  ].join(' ');
}

function buildInfographicBrief(context) {
  return [
    `Create a simple comparison infographic or chart brief for "${context.title}".`,
    'Use only information already present in the article.',
    'Prefer a chart only when the article contains clear numeric comparisons.',
    'If a chart is uncertain, produce a comparison infographic instead.',
  ].join(' ');
}

async function callAnthropicJson(task, payload, env) {
  const apiKey = env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error('Missing ANTHROPIC_API_KEY for visual planning.');
  }

  const model = env.ANTHROPIC_VISUAL_MODEL || env.ANTHROPIC_MODEL || 'claude-sonnet-4-6';
  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model,
      max_tokens: 2400,
      system: 'Return valid JSON only. Do not include markdown fences or commentary.',
      messages: [
        {
          role: 'user',
          content: JSON.stringify({ task, ...payload }),
        },
      ],
    }),
  });

  if (!response.ok) {
    throw new Error(`Anthropic request failed (${response.status}).`);
  }

  const data = await response.json();
  const text = (data.content || [])
    .filter((item) => item && item.type === 'text')
    .map((item) => item.text)
    .join('\n')
    .trim();

  return {
    model,
    data: parseJsonResponse(text),
  };
}

function parseJsonResponse(text) {
  const trimmed = String(text || '').trim().replace(/^```json/i, '').replace(/^```/i, '').replace(/```$/i, '').trim();
  const start = trimmed.indexOf('{');
  const end = trimmed.lastIndexOf('}');
  if (start === -1 || end === -1 || end < start) {
    throw new Error('Model returned no JSON object.');
  }
  return JSON.parse(trimmed.slice(start, end + 1));
}

async function planVisualAssets(article, env) {
  const context = buildVisualContext(article);
  const visualPolicy = getVisualPolicy(context.post_type, context.word_count);
  const response = await callAnthropicJson(
    'Create a structured visual plan for a WordPress draft upload pipeline.',
    {
      article: {
        title: context.title,
        slug: context.slug,
        excerpt: context.excerpt,
        meta_description: context.meta_description,
        headings: context.headings,
        draft_markdown: context.markdown,
        word_count: context.word_count,
      },
      output_schema: {
        featured_image: {
          needed: true,
          type: 'realistic_featured_image',
          placement: 'featured_media',
          filename: 'string',
          prompt: 'string',
          alt_text: 'string',
          caption: 'string',
          title: 'string',
          description: 'string',
        },
        content_visuals: [
          {
            needed: true,
            type: 'realistic_image',
            placement_after_heading: 'string',
            filename: 'string',
            prompt: 'string',
            alt_text: 'string',
            caption: 'string',
            title: 'string',
            description: 'string',
          },
          {
            needed: true,
            type: 'chart_or_infographic',
            subtype: 'chart or infographic',
            placement_after_heading: 'string',
            filename: 'string',
            prompt_or_spec: 'string',
            alt_text: 'string',
            caption: 'string',
            title: 'string',
            description: 'string',
          },
        ],
      },
      rules: [
        `Post-type visual target: ${visualPolicy.realistic_images} realistic support image(s) and ${visualPolicy.chart_or_infographic} chart/infographic visual(s), plus 1 featured image.`,
        'Do not add filler visuals.',
        'Featured image and realistic image must be realistic and text-free.',
        'Use exact heading text for placement_after_heading when possible.',
        'Choose chart only when the article contains clear numeric or comparison data.',
        'If no chart is justified, use infographic subtype.',
        'Use SEO-friendly filenames.',
        'Prioritise visual placement where it improves scanability or decision-making, not decorative symmetry.',
      ],
    },
    env,
  );

  return normalizeVisualPlan(response.data, article, env, response.model);
}

function normalizeVisualPlan(rawPlan, article, env, plannerModel) {
  const context = buildVisualContext(article);
  const visualPolicy = getVisualPolicy(context.post_type, context.word_count);
  const headings = extractHeadings(article.draft_markdown || '');
  const format = resolveRasterFormat(env.VISUALS_OUTPUT_FORMAT);
  const slugBase = slugify(context.slug, 'article');

  const featuredRaw = rawPlan && typeof rawPlan === 'object' ? rawPlan.featured_image || {} : {};
  const visualList = Array.isArray(rawPlan?.content_visuals) ? rawPlan.content_visuals : [];

  const plan = {
    planner_model: plannerModel,
    featured_image: {
      needed: featuredRaw.needed !== false,
      type: 'realistic_featured_image',
      placement: 'featured_media',
      filename: normalizeRasterFilename(featuredRaw.filename, `${slugBase}-featured-image`, format),
      prompt: String(featuredRaw.prompt || buildFeaturedPrompt(context)).trim(),
      // Featured image alt is the one we guarantee includes the primary keyword.
      alt_text: ensureKeywordInAltText(featuredRaw.alt_text, context.focus_keyword, context),
      caption: String(featuredRaw.caption || '').trim(),
      title: String(featuredRaw.title || context.title).trim(),
      description: String(featuredRaw.description || context.meta_description || context.excerpt || context.title).trim(),
    },
    content_visuals: [],
  };

  const normalizedVisuals = visualList
    .filter((item) => item && typeof item === 'object' && item.needed !== false)
    .map((visual, index) => {
      const type = visual.type === 'chart_or_infographic' ? 'chart_or_infographic' : 'realistic_image';
      const subtype = type === 'chart_or_infographic' && String(visual.subtype || '').toLowerCase() === 'chart'
        ? 'chart'
        : 'infographic';
      const baseName = type === 'chart_or_infographic'
        ? `${slugBase}-${subtype === 'chart' ? 'comparison-chart' : 'comparison-infographic'}-${index + 1}`
        : `${slugBase}-supporting-image-${index + 1}`;
      const placement = resolveHeadingMatch(headings, visual.placement_after_heading, type);

      return {
        needed: true,
        type,
        subtype,
        placement_after_heading: placement,
        filename: normalizeRasterFilename(visual.filename, baseName, format),
        prompt: type === 'realistic_image'
          ? String(visual.prompt || buildSupportingPrompt(context, placement)).trim()
          : undefined,
        prompt_or_spec: type === 'chart_or_infographic'
          ? String(visual.prompt_or_spec || buildInfographicBrief(context)).trim()
          : undefined,
        alt_text: String(visual.alt_text || context.title).trim(),
        caption: String(visual.caption || '').trim(),
        title: String(visual.title || context.title).trim(),
        description: String(visual.description || context.meta_description || context.title).trim(),
      };
    });

  const countByType = (type) => normalizedVisuals.filter((visual) => visual.type === type).length;
  const enoughWords = context.word_count >= 1200;

  while (countByType('realistic_image') < visualPolicy.realistic_images && enoughWords && headings.length) {
    const hint = visualPolicy.realistic_heading_hints[countByType('realistic_image')] || visualPolicy.realistic_heading_hints[0] || headings[0]?.text || '';
    const placement = resolveHeadingMatch(headings, hint, 'realistic_image');
    normalizedVisuals.push({
      needed: true,
      type: 'realistic_image',
      subtype: undefined,
      placement_after_heading: placement,
      filename: `${slugBase}-supporting-image-${countByType('realistic_image') + 1}.${format}`,
      prompt: buildSupportingPrompt(context, placement),
      prompt_or_spec: undefined,
      alt_text: context.title,
      caption: '',
      title: context.title,
      description: context.meta_description || context.title,
    });
  }

  while (countByType('chart_or_infographic') < visualPolicy.chart_or_infographic && enoughWords && headings.length) {
    const hint = visualPolicy.infographic_heading_hints[countByType('chart_or_infographic')] || visualPolicy.infographic_heading_hints[0] || headings[0]?.text || '';
    const useChart = articleContainsClearChartData(article.draft_markdown);
    const placement = resolveHeadingMatch(headings, hint, 'chart_or_infographic');
    normalizedVisuals.push({
      needed: true,
      type: 'chart_or_infographic',
      subtype: useChart ? 'chart' : 'infographic',
      placement_after_heading: placement,
      filename: `${slugBase}-${useChart ? 'comparison-chart' : 'comparison-infographic'}-${countByType('chart_or_infographic') + 1}.${format}`,
      prompt: undefined,
      prompt_or_spec: buildInfographicBrief(context),
      alt_text: context.title,
      caption: '',
      title: context.title,
      description: context.meta_description || context.title,
    });
  }

  const selectedVisuals = [];
  const realisticLimit = visualPolicy.realistic_images;
  const infographicLimit = visualPolicy.chart_or_infographic;
  let realisticCount = 0;
  let infographicCount = 0;
  normalizedVisuals.forEach((visual) => {
    if (visual.type === 'realistic_image' && realisticCount < realisticLimit) {
      selectedVisuals.push(visual);
      realisticCount += 1;
    } else if (visual.type === 'chart_or_infographic' && infographicCount < infographicLimit) {
      selectedVisuals.push(visual);
      infographicCount += 1;
    }
  });

  plan.content_visuals = selectedVisuals;
  return plan;
}

function articleContainsClearChartData(markdown) {
  const text = String(markdown || '');
  return /Estimated daily cost|Estimated monthly cost|Wattage range|25–35 cents|200W|300W|600W\+/i.test(text);
}

function resolveRasterFormat(format) {
  const value = String(format || 'webp').trim().toLowerCase();
  return ['webp', 'png', 'jpeg', 'jpg'].includes(value) ? value.replace('jpg', 'jpeg') : 'webp';
}

function normalizeRasterFilename(filename, fallbackBase, format) {
  const raw = String(filename || '').trim();
  const base = slugify(raw.replace(/\.[a-z0-9]+$/i, ''), fallbackBase);
  return `${base}.${format}`;
}

async function callOpenAIImage(prompt, env, outputPath) {
  const apiKey = env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error('Missing OPENAI_API_KEY for image generation.');
  }

  const outputFormat = resolveRasterFormat(env.VISUALS_OUTPUT_FORMAT);
  const payload = {
    model: env.OPENAI_IMAGE_MODEL || env.OPENAI_MODEL || 'gpt-image-1',
    prompt,
    size: '1536x1024',
    quality: 'medium',
    output_format: outputFormat,
  };

  const response = await fetch('https://api.openai.com/v1/images/generations', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`OpenAI image generation failed (${response.status}).`);
  }

  const data = await response.json();
  const item = Array.isArray(data.data) ? data.data[0] : null;
  if (!item || !item.b64_json) {
    throw new Error('OpenAI returned no image payload.');
  }

  fs.writeFileSync(outputPath, Buffer.from(item.b64_json, 'base64'));
  return {
    source_model: payload.model,
  };
}

async function requestAnthropicVisualSpec(article, visual, env) {
  const context = buildVisualContext(article);
  const response = await callAnthropicJson(
    'Create a chart or infographic specification for an article visual asset.',
    {
      article: {
        title: context.title,
        excerpt: context.excerpt,
        meta_description: context.meta_description,
        draft_markdown: context.markdown,
      },
      requested_visual: {
        type: visual.type,
        subtype: visual.subtype,
        placement_after_heading: visual.placement_after_heading,
        prompt_or_spec: visual.prompt_or_spec,
        alt_text: visual.alt_text,
        caption: visual.caption,
        title: visual.title,
        description: visual.description,
      },
      output_schema: {
        visual_type: 'chart or infographic',
        title: 'string',
        subtitle: 'string',
        caption: 'string',
        description: 'string',
        svg: 'string optional',
        chart_series: [{ label: 'string', value: 1, value_label: 'string' }],
        comparison_columns: {
          left_label: 'string',
          right_label: 'string',
          left_points: ['string'],
          right_points: ['string'],
        },
      },
      rules: [
        'Use only information that appears in the article.',
        'If numeric values are uncertain, do not invent them and prefer infographic output.',
        'Return JSON only.',
      ],
    },
    env,
  );

  return {
    source_model: response.model,
    spec: response.data,
  };
}

function isLikelyValidSvg(svg) {
  const text = String(svg || '').trim();
  return /<svg[\s>]/i.test(text) && /<\/svg>/i.test(text);
}

function escapeXml(value) {
  return String(value ?? '').replace(/[<>&'"]/g, (match) => ({
    '<': '&lt;',
    '>': '&gt;',
    '&': '&amp;',
    "'": '&apos;',
    '"': '&quot;',
  }[match]));
}

function renderChartSvg(spec, outputPath) {
  const width = 1200;
  const height = 820;
  const chartHeight = 360;
  const chartBaseY = 620;
  const chartLeft = 110;
  const chartWidth = 920;
  const series = Array.isArray(spec.chart_series) ? spec.chart_series.slice(0, 4) : [];
  const maxValue = Math.max(...series.map((item) => Number(item.value) || 0), 1);
  const barWidth = Math.max(140, Math.floor(chartWidth / Math.max(series.length, 1)) - 40);

  const bars = series.map((item, index) => {
    const value = Number(item.value) || 0;
    const barHeight = Math.max(18, Math.round((value / maxValue) * chartHeight));
    const x = chartLeft + index * (barWidth + 40);
    const y = chartBaseY - barHeight;
    return [
      `<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="20" fill="#356c71"/>`,
      `<text x="${x + barWidth / 2}" y="${y - 18}" text-anchor="middle" font-size="24" fill="#1f2937">${escapeXml(item.value_label || value)}</text>`,
      `<text x="${x + barWidth / 2}" y="${chartBaseY + 36}" text-anchor="middle" font-size="24" fill="#1f2937">${escapeXml(item.label || `Item ${index + 1}`)}</text>`,
    ].join('');
  }).join('\n');

  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#f7f4ef"/>
  <text x="80" y="92" font-size="44" font-weight="700" fill="#111827">${escapeXml(spec.title || 'Comparison Chart')}</text>
  <text x="80" y="132" font-size="24" fill="#4b5563">${escapeXml(spec.subtitle || '')}</text>
  <line x1="${chartLeft}" y1="${chartBaseY}" x2="${chartLeft + chartWidth}" y2="${chartBaseY}" stroke="#94a3b8" stroke-width="3"/>
  ${bars}
</svg>`;

  fs.writeFileSync(outputPath, svg, 'utf8');
}

function renderComparisonSvg(spec, outputPath) {
  const width = 1200;
  const height = 820;
  const leftPoints = Array.isArray(spec.comparison_columns?.left_points) ? spec.comparison_columns.left_points.slice(0, 5) : [];
  const rightPoints = Array.isArray(spec.comparison_columns?.right_points) ? spec.comparison_columns.right_points.slice(0, 5) : [];
  const leftLabel = spec.comparison_columns?.left_label || 'Option A';
  const rightLabel = spec.comparison_columns?.right_label || 'Option B';

  const renderPoints = (points, startX) => points.map((point, index) => {
    const y = 250 + index * 80;
    return `<circle cx="${startX}" cy="${y - 8}" r="9" fill="#356c71"/><text x="${startX + 24}" y="${y}" font-size="24" fill="#1f2937">${escapeXml(point)}</text>`;
  }).join('\n');

  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#f7f4ef"/>
  <text x="80" y="92" font-size="44" font-weight="700" fill="#111827">${escapeXml(spec.title || 'Comparison Infographic')}</text>
  <text x="80" y="132" font-size="24" fill="#4b5563">${escapeXml(spec.subtitle || '')}</text>
  <rect x="80" y="180" width="480" height="560" rx="28" fill="#ffffff" stroke="#d6d3d1"/>
  <rect x="640" y="180" width="480" height="560" rx="28" fill="#ffffff" stroke="#d6d3d1"/>
  <text x="120" y="230" font-size="32" font-weight="700" fill="#356c71">${escapeXml(leftLabel)}</text>
  <text x="680" y="230" font-size="32" font-weight="700" fill="#356c71">${escapeXml(rightLabel)}</text>
  ${renderPoints(leftPoints, 126)}
  ${renderPoints(rightPoints, 686)}
</svg>`;

  fs.writeFileSync(outputPath, svg, 'utf8');
}

function specLooksNumeric(spec, article) {
  const series = Array.isArray(spec.chart_series) ? spec.chart_series : [];
  if (!series.length) {
    return false;
  }
  const articleText = String(article.draft_markdown || '');
  return series.every((item) => {
    const valueLabel = String(item.value_label || item.value || '').trim();
    return valueLabel && articleText.includes(valueLabel);
  });
}

async function convertSvgToRaster(svgPath, rasterPath, format) {
  const candidates = [
    () => require('sharp'),
    () => require(path.join(__dirname, '..', 'apps', 'web', 'node_modules', 'sharp')),
  ];

  let sharp = null;
  for (const candidate of candidates) {
    try {
      sharp = candidate();
      break;
    } catch (_error) {
      sharp = null;
    }
  }

  if (!sharp) {
    return false;
  }

  const pipeline = sharp(svgPath);
  if (format === 'png') {
    await pipeline.png().toFile(rasterPath);
  } else if (format === 'jpeg') {
    await pipeline.jpeg({ quality: 92 }).toFile(rasterPath);
  } else {
    await pipeline.webp({ quality: 92 }).toFile(rasterPath);
  }
  return true;
}

function createVisualMetadata(visual, filename, sourceModel) {
  return {
    type: visual.type,
    source_model: sourceModel,
    filename,
    alt_text: visual.alt_text || '',
    caption: visual.caption || '',
    title: visual.title || '',
    description: visual.description || '',
    placement: visual.type === 'realistic_featured_image' ? 'featured_media' : 'content',
    placement_after_heading: visual.placement_after_heading || '',
    wordpress_media_id: null,
    wordpress_media_url: null,
  };
}

function writeVisualMetadata(asset) {
  writeJson(asset.metadataPath, asset.metadata);
}

async function generateVisualAssets(articlePath, article, env) {
  const result = {
    enabled: String(env.VISUALS_ENABLED || 'true').toLowerCase() === 'true',
    folder: null,
    plan: null,
    visuals: [],
    warnings: [],
  };

  if (!result.enabled) {
    return result;
  }

  result.folder = path.join(articlePath, 'visual-assets');
  ensureDir(result.folder);

  try {
    result.plan = await planVisualAssets(article, env);
    writeJson(path.join(result.folder, 'visual-plan.json'), result.plan);
  } catch (error) {
    result.warnings.push(`Visual planning skipped: ${error.message}`);
    return result;
  }

  const rasterFormat = resolveRasterFormat(env.VISUALS_OUTPUT_FORMAT);
  const featured = result.plan.featured_image;
  if (featured?.needed) {
    const outputPath = path.join(result.folder, featured.filename);
    const metadataPath = outputPath.replace(/\.[^.]+$/, '.json');
    const asset = {
      kind: 'featured',
      path: null,
      svgPath: null,
      metadataPath,
      metadata: createVisualMetadata({ ...featured, type: 'realistic_featured_image' }, path.basename(outputPath), env.OPENAI_IMAGE_MODEL || env.OPENAI_MODEL || 'gpt-image-1'),
    };

    try {
      const response = await callOpenAIImage(featured.prompt, env, outputPath);
      asset.path = outputPath;
      asset.metadata.source_model = response.source_model;
      writeVisualMetadata(asset);
      result.visuals.push(asset);
    } catch (error) {
      result.warnings.push(`Featured image generation failed: ${error.message}`);
    }
  }

  for (const visual of result.plan.content_visuals || []) {
    if (!visual.needed) continue;

    if (visual.type === 'realistic_image') {
      const outputPath = path.join(result.folder, visual.filename);
      const metadataPath = outputPath.replace(/\.[^.]+$/, '.json');
      const asset = {
        kind: 'content',
        path: null,
        svgPath: null,
        metadataPath,
        metadata: createVisualMetadata(visual, path.basename(outputPath), env.OPENAI_IMAGE_MODEL || env.OPENAI_MODEL || 'gpt-image-1'),
      };

      try {
        const response = await callOpenAIImage(visual.prompt, env, outputPath);
        asset.path = outputPath;
        asset.metadata.source_model = response.source_model;
        writeVisualMetadata(asset);
        result.visuals.push(asset);
      } catch (error) {
        result.warnings.push(`Supporting image generation failed for "${visual.placement_after_heading || 'content section'}": ${error.message}`);
      }
      continue;
    }

    const outputPath = path.join(result.folder, visual.filename);
    const svgPath = outputPath.replace(/\.[^.]+$/, '.svg');
    const metadataPath = outputPath.replace(/\.[^.]+$/, '.json');
    const asset = {
      kind: 'content',
      path: null,
      svgPath: null,
      metadataPath,
      metadata: createVisualMetadata(visual, path.basename(outputPath), env.ANTHROPIC_VISUAL_MODEL || env.ANTHROPIC_MODEL || 'claude-sonnet-4-6'),
    };

    try {
      const response = await requestAnthropicVisualSpec(article, visual, env);
      asset.metadata.source_model = response.source_model;

      if (response.spec.svg && isLikelyValidSvg(response.spec.svg)) {
        fs.writeFileSync(svgPath, response.spec.svg, 'utf8');
      } else if (response.spec.visual_type === 'chart' && specLooksNumeric(response.spec, article)) {
        renderChartSvg(response.spec, svgPath);
      } else {
        renderComparisonSvg(response.spec, svgPath);
      }

      asset.svgPath = svgPath;
      const converted = await convertSvgToRaster(svgPath, outputPath, rasterFormat);
      if (converted) {
        asset.path = outputPath;
        asset.metadata.filename = path.basename(outputPath);
      } else {
        result.warnings.push(`Saved SVG for "${visual.title}" locally, but raster conversion was unavailable. WordPress upload skipped for this visual.`);
        asset.metadata.filename = path.basename(svgPath);
      }

      if (response.spec.caption && !asset.metadata.caption) {
        asset.metadata.caption = String(response.spec.caption).trim();
      }
      if (response.spec.description && !asset.metadata.description) {
        asset.metadata.description = String(response.spec.description).trim();
      }

      writeVisualMetadata(asset);
      result.visuals.push(asset);
    } catch (error) {
      result.warnings.push(`Chart or infographic generation failed for "${visual.placement_after_heading || 'comparison section'}": ${error.message}`);
    }
  }

  return result;
}

function buildFigureHtml(visual) {
  const captionHtml = visual.metadata.caption ? `\n  <figcaption>${escapeHtml(visual.metadata.caption)}</figcaption>` : '';
  return `<figure class="hdl-image-block">\n  <img src="${escapeHtml(visual.metadata.wordpress_media_url)}" alt="${escapeHtml(visual.metadata.alt_text || '')}" loading="lazy">${captionHtml}\n</figure>`;
}

function insertFeaturedFigure(html, visual) {
  if (!visual?.metadata?.wordpress_media_url) {
    return html;
  }
  const figure = buildFigureHtml(visual);
  const tocClose = '</nav>';
  const tocIndex = html.indexOf(tocClose);
  if (tocIndex !== -1) {
    const insertAt = tocIndex + tocClose.length;
    return `${html.slice(0, insertAt)}\n${figure}${html.slice(insertAt)}`;
  }
  const firstH2Match = html.match(/<h2\b[^>]*>/i);
  if (firstH2Match && typeof firstH2Match.index === 'number') {
    return `${html.slice(0, firstH2Match.index)}${figure}\n${html.slice(firstH2Match.index)}`;
  }
  return `${html}\n${figure}`;
}

function findHeadingForInsertion(html, requestedHeading, visual) {
  const regex = /<h([23])[^>]*>([\s\S]*?)<\/h\1>/gi;
  const headings = [];
  let match;

  while ((match = regex.exec(html)) !== null) {
    const text = match[2].replace(/<[^>]+>/g, '').trim();
    headings.push({
      text,
      normalized: normalizeText(text),
      endIndex: match.index + match[0].length,
    });
  }

  if (!headings.length) {
    return null;
  }

  const exactTarget = normalizeText(requestedHeading);
  if (exactTarget) {
    const exact = headings.find((heading) => heading.normalized === exactTarget);
    if (exact) {
      return exact;
    }
  }

  const keywords = new Set(normalizeText(requestedHeading).split(' ').filter((word) => word.length > 2));
  let bestScore = 0;
  let bestHeading = null;
  for (const heading of headings) {
    const score = heading.normalized.split(' ').reduce((sum, word) => sum + (keywords.has(word) ? 1 : 0), 0);
    if (score > bestScore) {
      bestScore = score;
      bestHeading = heading;
    }
  }
  if (bestHeading && bestScore > 0) {
    return bestHeading;
  }

  const preferredRegex = visual.metadata.type === 'chart_or_infographic'
    ? /cost|compare|comparison|running|buying|recommendation/i
    : /context|dehumidifier|air purifier|recommendation|cleaning/i;
  return headings.find((heading) => preferredRegex.test(heading.text)) || null;
}

function injectFigures(html, visuals, warnings) {
  let output = html;
  let inserted = 0;

  for (const visual of visuals) {
    if (!visual.metadata.wordpress_media_url || visual.metadata.placement !== 'content') {
      continue;
    }

    const heading = findHeadingForInsertion(output, visual.metadata.placement_after_heading, visual);
    if (!heading) {
      warnings.push(`Skipped HTML insertion for ${visual.metadata.filename}: no suitable H2/H3 heading was found.`);
      continue;
    }

    const figure = buildFigureHtml(visual);
    output = `${output.slice(0, heading.endIndex)}\n${figure}${output.slice(heading.endIndex)}`;
    inserted += 1;
  }

  return { html: output, inserted };
}

function mimeTypeForPath(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  switch (extension) {
    case '.png':
      return 'image/png';
    case '.jpeg':
    case '.jpg':
      return 'image/jpeg';
    case '.webp':
      return 'image/webp';
    default:
      return 'application/octet-stream';
  }
}

async function uploadMediaAsset(baseUrl, username, appPassword, filePath) {
  const credentials = Buffer.from(`${username}:${appPassword}`).toString('base64');
  const body = fs.readFileSync(filePath);
  const response = await fetch(`${baseUrl.replace(/\/$/, '')}/wp-json/wp/v2/media`, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${credentials}`,
      'Content-Disposition': `attachment; filename="${path.basename(filePath)}"`,
      'Content-Type': mimeTypeForPath(filePath),
      'User-Agent': 'ContentMachine/1.0',
    },
    body,
  });

  if (!response.ok) {
    throw new Error(`WordPress media upload failed (${response.status}).`);
  }

  const data = await response.json();
  return {
    media_id: data.id,
    media_url: data.source_url,
  };
}

async function updateWordPressMediaMetadata(baseUrl, username, appPassword, mediaId, metadata) {
  const payload = {
    alt_text: metadata.alt_text || '',
    caption: metadata.caption || '',
    description: metadata.description || '',
    title: metadata.title || '',
  };

  return makeWordPressRequest(
    'POST',
    `/wp-json/wp/v2/media/${mediaId}`,
    JSON.stringify(payload),
    baseUrl,
    username,
    appPassword,
  );
}

function readArticle(articlePath) {
  const draftsPath = path.join(articlePath, 'drafts');
  const articleJsonPath = path.join(articlePath, 'article.json');
  const jsonPath = fileExists(path.join(draftsPath, 'latest.json'))
    ? path.join(draftsPath, 'latest.json')
    : path.join(draftsPath, 'draft-v3-final.json');

  if (!fileExists(jsonPath)) {
    throw new Error(`No source JSON found in ${draftsPath}`);
  }

  const draftArticle = readJson(jsonPath);
  const rootArticle = fileExists(articleJsonPath) ? readJson(articleJsonPath) : {};

  return {
    jsonPath,
    article: {
      ...rootArticle,
      ...draftArticle,
      post_type: draftArticle.post_type || rootArticle.post_type || 'informational_blog',
    },
  };
}

function buildArticleHtml(article) {
  return renderArticleHtml(article.draft_markdown || '', {
    post_type: article.post_type || 'informational_blog',
    content_modules: article.content_modules || article.source_payload_json?.content_modules || [],
    wordpressBlocks: true,
  });
}

function formatWarningList(warnings) {
  return warnings.length ? warnings.map((warning) => `Warning: ${warning}`) : [];
}

async function uploadArticleToWordPress(articlePath, env) {
  const { jsonPath, article } = readArticle(articlePath);
  const baseUrl = env.WORDPRESS_BASE_URL || env.WORDPRESS_SITE_URL;
  const username = env.WORDPRESS_USERNAME;
  const appPassword = env.WORDPRESS_APP_PASSWORD;

  if (!baseUrl || !username || !appPassword) {
    throw new Error('Missing WordPress credentials. Required: WORDPRESS_BASE_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD');
  }
  if (!article.draft_markdown) {
    throw new Error('No draft_markdown found in source JSON.');
  }

  const htmlPath = path.join(articlePath, `${article.slug || 'article'}.html`);
  let finalHtml = buildArticleHtml(article);
  fs.writeFileSync(htmlPath, finalHtml, 'utf8');

  const visualWarnings = [];
  const visualRun = await generateVisualAssets(articlePath, article, env);
  visualWarnings.push(...visualRun.warnings);
  let insertedVisuals = 0;
  const uploadedVisuals = [];

  if (visualRun.enabled && visualRun.plan) {
    console.log('Generating visuals...');
    console.log(`Visual plan saved: ${path.join(visualRun.folder, 'visual-plan.json')}`);
    console.log('Uploading media...');

    for (const visual of visualRun.visuals) {
      if (!visual.path || !fileExists(visual.path)) {
        continue;
      }

      try {
        const uploaded = await uploadMediaAsset(baseUrl, username, appPassword, visual.path);
        visual.metadata.wordpress_media_id = uploaded.media_id;
        visual.metadata.wordpress_media_url = uploaded.media_url;

        try {
          await updateWordPressMediaMetadata(baseUrl, username, appPassword, uploaded.media_id, visual.metadata);
        } catch (error) {
          visualWarnings.push(`Media metadata update failed for ${path.basename(visual.path)}: ${error.message}`);
        }

        writeVisualMetadata(visual);
        uploadedVisuals.push(visual);
      } catch (error) {
        visualWarnings.push(`Media upload failed for ${path.basename(visual.path)}: ${error.message}`);
      }
    }

    console.log('Inserting images...');
    const injection = injectFigures(finalHtml, uploadedVisuals, visualWarnings);
    finalHtml = injection.html;
    insertedVisuals = injection.inserted;

    const featuredVisual = uploadedVisuals.find((visual) => visual.metadata.placement === 'featured_media');
    finalHtml = insertFeaturedFigure(finalHtml, featuredVisual);
    fs.writeFileSync(htmlPath, finalHtml, 'utf8');
  }

  const featuredVisual = uploadedVisuals.find((visual) => visual.metadata.placement === 'featured_media');

  // Rank Math focus keyword: source from the article's primary keyword (never invented).
  const focusKeyword = resolvePrimaryKeyword(article);

  // Warn (only) when no real external/internal links are present. Never inserts links.
  const linkAnalysis = analyseLinks(finalHtml, baseUrl);
  visualWarnings.push(...linkAnalysis.warnings);

  const postData = {
    title: article.seo_title || extractH1(article.draft_markdown) || article.slug || 'Article',
    content: finalHtml,
    status: 'draft',
    slug: article.slug || undefined,
    excerpt: article.excerpt || undefined,
    featured_media: featuredVisual?.metadata.wordpress_media_id || undefined,
    // Rank Math reads these post meta keys. Only set them when we actually have a value;
    // they are removed below if undefined so we never overwrite existing meta with blanks.
    meta: {
      rank_math_focus_keyword: focusKeyword || undefined,
      rank_math_description: article.meta_description || undefined,
    },
  };
  // Drop the meta object entirely if neither value is present.
  if (postData.meta && !postData.meta.rank_math_focus_keyword && !postData.meta.rank_math_description) {
    delete postData.meta;
  } else if (postData.meta) {
    Object.keys(postData.meta).forEach((key) => postData.meta[key] === undefined && delete postData.meta[key]);
  }
  Object.keys(postData).forEach((key) => postData[key] === undefined && delete postData[key]);

  console.log(`Local source JSON: ${jsonPath}`);
  console.log(`Generated HTML path: ${htmlPath}`);
  console.log(`WordPress endpoint: ${baseUrl.replace(/\/$/, '')}/wp-json/wp/v2/posts`);
  console.log('Status: draft');
  console.log('Uploading WordPress draft...');

  const response = await makeWordPressRequest(
    'POST',
    '/wp-json/wp/v2/posts',
    JSON.stringify(postData),
    baseUrl,
    username,
    appPassword,
  );

  if (response.status !== 201 || !response.data) {
    throw new Error(`Unexpected response status: ${response.status}`);
  }

  const postId = response.data.id;
  const editLink = `${baseUrl.replace(/\/$/, '')}/wp-admin/post.php?post=${postId}&action=edit`;
  const enhancedPath = path.join(articlePath, 'article.with-html.json');
  writeJson(enhancedPath, {
    ...article,
    content_html: finalHtml,
    rank_math_focus_keyword: focusKeyword || null,
    wordpress_post_id: postId,
    wordpress_status: 'draft',
    visual_assets_folder: visualRun.folder,
  });

  return {
    postId,
    editLink,
    htmlPath,
    visualAssetsFolder: visualRun.folder,
    featuredMediaId: featuredVisual?.metadata.wordpress_media_id || null,
    insertedVisuals,
    warnings: visualWarnings,
  };
}

async function main() {
  try {
    const args = process.argv.slice(2);
    let articlePath = null;

    for (let index = 0; index < args.length; index += 1) {
      if (args[index] === '--article' && args[index + 1]) {
        articlePath = args[index + 1];
        index += 1;
      }
    }

    if (!articlePath) {
      console.error('Error: Please specify article path');
      console.error('\nUsage: npm run upload:wordpress -- --article "D:\\path\\to\\article"');
      process.exit(1);
    }

    if (!fileExists(articlePath)) {
      console.error(`Error: Article path does not exist: ${articlePath}`);
      process.exit(1);
    }

    const env = loadEnv();
    const result = await uploadArticleToWordPress(articlePath, env);
    console.log('========================================');
    console.log(`WordPress post ID: ${result.postId}`);
    console.log(`WordPress draft post ID: ${result.postId}`);
    console.log(`Edit URL: ${result.editLink}`);
    console.log(`Generated HTML path: ${result.htmlPath}`);
    console.log(`Visual assets folder: ${result.visualAssetsFolder || '(disabled)'}`);
    if (result.featuredMediaId) {
      console.log(`Featured image media ID: ${result.featuredMediaId}`);
    }
    console.log(`In-content images inserted: ${result.insertedVisuals}`);
    formatWarningList(result.warnings).forEach((warning) => console.log(warning));
    console.log('Status: draft only');
    console.log('========================================\n');
  } catch (error) {
    console.error(`\nError: ${error.message}\n`);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
