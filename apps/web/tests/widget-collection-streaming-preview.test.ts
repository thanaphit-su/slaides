import { describe, it, expect } from 'vitest';
import { extractPreviewFields, sanitizeStreamingHtml } from '../src/widgets/streaming-parser';

describe('extractPreviewFields', () => {
  it('extracts html after string closes', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<div>Hello</div>","css":""}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<div>Hello</div>');
    expect(fields.name).toBe('Test');
  });
  
  it('handles escaped quotes in HTML', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<div class=\\"card\\">Hi</div>","css":""}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<div class="card">Hi</div>');
  });
  
  it('handles \\n and \\uXXXX escapes', () => {
    const json = '{"type":"draft","widget":{"name":"Test\\u00A9","html":"Line1\\nLine2","css":""}}';
    const fields = extractPreviewFields(json);
    expect(fields.name).toBe('Test©');
    expect(fields.html).toBe('Line1\nLine2');
  });
  
  it('does not extract nested props_schema.html', () => {
    const json = '{"type":"draft","widget":{"name":"Test","props_schema":{"html":{"type":"string"}},"html":"<div>Real</div>"}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<div>Real</div>');
  });
  
  it('returns null for incomplete html string', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<div class=\\"';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBeNull();
  });
  
  it('extracts css field', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<div/>","css":".card { color: red; }"}}';
    const fields = extractPreviewFields(json);
    expect(fields.css).toBe('.card { color: red; }');
  });
  
  it('handles incomplete escape sequences', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<div>Test\\\\';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBeNull();
  });
  
  it('extracts kind field', () => {
    const json = '{"type":"draft","widget":{"name":"Test","kind":"poll","html":"<div/>","css":""}}';
    const fields = extractPreviewFields(json);
    expect(fields.kind).toBe('poll');
  });
  
  it('handles markdown code fences', () => {
    const json = '```json\n{"type":"draft","widget":{"name":"Test","html":"<div>Hi</div>","css":""}}\n```';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<div>Hi</div>');
  });
  
  it('handles escaped backslashes', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<div>Path:\\\\foo</div>","css":""}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<div>Path:\\foo</div>');
  });
  
  it('handles escaped forward slash', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<script>var x = 1<\\/script>","css":""}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<script>var x = 1</script>');
  });
  
  it('returns null when widget object not found', () => {
    const json = '{"type":"draft","plan":["step 1"]}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBeNull();
    expect(fields.name).toBeNull();
  });
  
  it('extracts multiple fields from complete JSON', () => {
    const json = '{"type":"draft","widget":{"name":"Poll Widget","kind":"custom","html":"<div>Poll</div>","css":".poll{}"}}';
    const fields = extractPreviewFields(json);
    expect(fields.name).toBe('Poll Widget');
    expect(fields.kind).toBe('custom');
    expect(fields.html).toBe('<div>Poll</div>');
    expect(fields.css).toBe('.poll{}');
  });
  
  it('handles nested example_props without confusion', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<div>Real</div>","example_props":{"name":"fake","html":"fake"}}}}';
    const fields = extractPreviewFields(json);
    expect(fields.name).toBe('Test');
    expect(fields.html).toBe('<div>Real</div>');
  });
  
  it('does not match widget inside string content', () => {
    const json = '{"type":"draft","widget":{"name":"Test","html":"<div>Text with \\"widget\\": {fake}</div>","css":""}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<div>Text with "widget": {fake}</div>');
    expect(fields.name).toBe('Test');
  });
  
  it('finds widget key not first object', () => {
    const json = '{"type":"draft","metadata":{"foo":"bar"},"widget":{"name":"Test","html":"<div>Hi</div>","css":""}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<div>Hi</div>');
    expect(fields.name).toBe('Test');
  });
  
  it('ignores non-widget objects', () => {
    const json = '{"type":"draft","metadata":{"html":"fake"},"plan":["step1"]}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBeNull();
  });
  
  it('finds top-level widget not nested widget', () => {
    const json = '{"type":"draft","metadata":{"widget":{"html":"fake"}},"widget":{"html":"real","name":"Test"}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('real');
    expect(fields.name).toBe('Test');
  });
  
  it('finds widget when nested object comes first', () => {
    const json = '{"type":"draft","config":{"widget":{"nested":true}},"widget":{"html":"<div>Real</div>","name":"Test"}}';
    const fields = extractPreviewFields(json);
    expect(fields.html).toBe('<div>Real</div>');
    expect(fields.name).toBe('Test');
  });
});

describe('sanitizeStreamingHtml', () => {
  it('strips <script> tags', () => {
    const html = '<div>Hello</div><script>alert("xss")</script><p>World</p>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div>Hello</div><p>World</p>');
  });
  
  it('preserves basic structural HTML', () => {
    const html = '<div class="card"><h1>Title</h1><p>Content</p></div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="card"><h1>Title</h1><p>Content</p></div>');
  });
  
  it('strips onclick attributes', () => {
    const html = '<div onclick="alert(1)" class="safe">Text</div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="safe">Text</div>');
  });
  
  it('strips multiple event handlers', () => {
    const html = '<div onclick="a()" onmouseover="b()" class="safe">Text</div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="safe">Text</div>');
  });
  
  it('strips <svg> elements', () => {
    const html = '<div>Before</div><svg onload="alert(1)"><circle/></svg><div>After</div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div>Before</div><div>After</div>');
  });
  
  it('strips <iframe> elements', () => {
    const html = '<div>Content</div><iframe src="https://evil.com"></iframe>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div>Content</div>');
  });
  
  it('strips <form> elements', () => {
    const html = '<form action="/submit"><input type="text"></form>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('');
  });
  
  it('strips <img> elements (no remote resources)', () => {
    const html = '<div>Text</div><img src="https://example.com/pic.jpg" alt="Pic">';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div>Text</div>');
  });
  
  it('strips href attributes (no remote URLs)', () => {
    const html = '<a href="https://example.com" class="link">Link</a>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<a class="link">Link</a>');
  });
  
  it('strips style attributes', () => {
    const html = '<div style="background:url(javascript:alert(1))" class="safe">Text</div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="safe">Text</div>');
  });
  
  it('strips javascript: URLs in href', () => {
    const html = '<a href="javascript:alert(1)" class="link">Click</a>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<a class="link">Click</a>');
  });
  
  it('strips HTML-entity encoded javascript: URLs', () => {
    const html = '<a href="java&#x73;cript:alert(1)" class="link">Click</a>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<a class="link">Click</a>');
  });
  
  it('strips named entity encoded javascript: URLs', () => {
    const html = '<a href="javascript&colon;alert(1)" class="link">Click</a>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<a class="link">Click</a>');
  });
  
  it('preserves class and id attributes', () => {
    const html = '<div id="main" class="container"><span class="text">Hi</span></div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="container" id="main"><span class="text">Hi</span></div>');
  });
  
  it('preserves only class and id, strips all others', () => {
    const html = '<div id="main" class="container" data-value="123" aria-label="test">Content</div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="container" id="main">Content</div>');
  });
  
  it('strips non-whitelisted tags but keeps content', () => {
    const html = '<div><custom-tag class="x">Inner</custom-tag></div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div>Inner</div>');
  });
  
  it('strips <button> elements (interactive)', () => {
    const html = '<button onclick="bad()" class="btn">Click</button>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('');
  });
  
  it('strips <input> elements (interactive)', () => {
    const html = '<input type="text" value="test">';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('');
  });
  
  it('strips <style> tags', () => {
    const html = '<div>Text</div><style>.x { color: red; }</style>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div>Text</div>');
  });
  
  it('strips <link> tags', () => {
    const html = '<head><link rel="stylesheet" href="evil.css"></head>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('');
  });
  
  it('strips <video> elements', () => {
    const html = '<video src="video.mp4"></video>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('');
  });
  
  it('strips <canvas> elements', () => {
    const html = '<canvas id="c"></canvas>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('');
  });
  
  it('strips bare attributes (contenteditable)', () => {
    const html = '<div contenteditable class="x">Text</div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="x">Text</div>');
  });
  
  it('strips bare attributes (disabled)', () => {
    const html = '<button disabled>Click</button>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('');  // button is not allowed
  });
  
  it('preserves only class and id, strips all others', () => {
    const html = '<div id="main" class="container" data-value="123" aria-label="test">Content</div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="container" id="main">Content</div>');
  });
  
  it('escapes quotes in class/id values to prevent attribute injection', () => {
    // The &quot; entity in the source gets double-escaped, proving escaping works
    const html = `<div class="test&quot;">Text</div>`;
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="test&amp;quot;">Text</div>');
  });
  
  it('escapes ampersands in class/id values', () => {
    const html = '<div class="test&value">Text</div>';
    const sanitized = sanitizeStreamingHtml(html);
    expect(sanitized).toBe('<div class="test&amp;value">Text</div>');
  });
});
