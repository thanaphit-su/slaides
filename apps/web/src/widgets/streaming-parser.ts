/**
 * State-machine parser for extracting widget preview fields from streaming JSON.
 * Exported for testing.
 */

export interface StreamingPreviewFields {
  html: string | null;
  css: string | null;
  name: string | null;
  kind: string | null;
}

type ParseMode = "key" | "colon" | "value" | "skip";

export function extractPreviewFields(raw: string): StreamingPreviewFields {
  const source = stripCodeFence(raw);
  
  const widgetStart = findWidgetObjectStart(source);
  if (widgetStart === -1) {
    return { html: null, css: null, name: null, kind: null };
  }
  
  const result = extractTopLevelFields(source, widgetStart, ['html', 'css', 'name', 'kind']);
  
  return {
    html: result.html || null,
    css: result.css || null,
    name: result.name || null,
    kind: result.kind || null,
  };
}

function stripCodeFence(text: string): string {
  const trimmed = text.trim();
  const match = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  return match ? match[1].trim() : trimmed;
}

export function findWidgetObjectStart(source: string): number {
  let inString = false;
  let escapeMode = false;
  let keyStart = -1;
  let depth = -1;  // Start at -1, first '{' brings us to 0 (root object)
  
  for (let i = 0; i < source.length; i++) {
    const char = source[i];
    
    if (escapeMode) {
      escapeMode = false;
      continue;
    }
    
    if (char === '\\') {
      if (inString) escapeMode = true;
      continue;
    }
    
    if (char === '"') {
      if (!inString) {
        inString = true;
        keyStart = i + 1;
      } else {
        inString = false;
        const key = source.substring(keyStart, i);
        
        // Only match "widget" at depth 0 (top level of root object)
        if (key === 'widget' && depth === 0) {
          // Check if next non-space char is ':'
          let j = i + 1;
          while (j < source.length && /\s/.test(source[j])) j++;
          if (source[j] === ':') {
            // Found "widget": - now find the opening brace
            j++;
            while (j < source.length && /\s/.test(source[j])) j++;
            if (source[j] === '{') {
              return j + 1;  // Return position after '{'
            }
          }
        }
      }
      continue;
    }
    
    // Track depth changes (only when not in string)
    if (!inString && (char === '{' || char === '[')) {
      depth += 1;
    } else if (!inString && (char === '}' || char === ']')) {
      depth -= 1;
    }
  }
  
  return -1;
}

export function extractTopLevelFields(
  source: string,
  start: number,
  fieldNames: string[]
): Record<string, string | null> {
  const result: Record<string, string | null> = {};
  for (const name of fieldNames) {
    result[name] = null;
  }
  
  let depth = 1;
  let inString = false;
  let escapeMode = false;
  let mode: ParseMode = "key";
  let pendingKey: string | null = null;
  let stringValue = "";
  
  for (let i = start; i < source.length; i++) {
    const char = source[i];
    
    if (escapeMode) {
      if (inString) {
        stringValue += char;
      }
      escapeMode = false;
      continue;
    }
    
    if (char === '\\') {
      if (inString) {
        escapeMode = true;
        if (mode === "value") {
          stringValue += char;
        }
      }
      continue;
    }
    
    if (char === '"') {
      if (!inString) {
        inString = true;
        stringValue = "";
      } else {
        if (mode === "key" && depth === 1) {
          pendingKey = stringValue;
          mode = "colon";
        } else if (mode === "value" && pendingKey && depth === 1) {
          if (fieldNames.includes(pendingKey)) {
            try {
              result[pendingKey] = JSON.parse(`"${stringValue}"`) as string;
            } catch {
              // Incomplete escape or invalid JSON - skip
            }
          }
          pendingKey = null;
          mode = "skip";
        }
        stringValue = "";
        inString = false;
      }
      continue;
    }
    
    if (inString) {
      stringValue += char;
      continue;
    }
    
    if (char === ':' && !inString) {
      if (mode === "colon" && pendingKey) {
        mode = "value";
      }
      continue;
    }
    
    if (!inString) {
      if (char === '{' || char === '[') {
        if (mode === "value") {
          mode = "skip";
          pendingKey = null;
        }
        depth += 1;
      } else if (char === '}' || char === ']') {
        depth -= 1;
        if (depth < 1) {
          break;
        }
        pendingKey = null;
        mode = depth === 1 ? "key" : "skip";
      } else if (char === ',' && depth === 1) {
        mode = "key";
        pendingKey = null;
      }
      
      if (mode === "value" && depth === 1 && !inString && /[a-z0-9-]/.test(char)) {
        mode = "skip";
        pendingKey = null;
      }
    }
  }
  
  return result;
}

/**
 * Sanitize HTML for streaming preview using a strict allowlist approach.
 * 
 * SECURITY MODEL: Streaming preview renders BEFORE validation, so we assume
 * the HTML could be malicious. We use a conservative allowlist:
 * - Only basic layout/content tags (no forms, no embedded content)
 * - Only inert attributes (no URLs, no styles, no event handlers)
 * - No remote resource fetches (strip all href, src, and CSS URLs)
 * 
 * This ensures NO network requests and NO script execution during streaming.
 */
export function sanitizeStreamingHtml(html: string): string {
  return sanitizeHtmlStrict(html);
}

/**
 * Strict allowlist-based sanitizer for streaming preview.
 * Only allows safe structural/content tags with inert attributes.
 */
function sanitizeHtmlStrict(html: string): string {
  let sanitized = html;
  
  // ALLOWED tags: basic layout and content only (no interactive, no media, no forms)
  const ALLOWED_TAGS = new Set([
    'div', 'span', 'p', 'br', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'strong', 'b', 'em', 'i', 'u', 's',
    'a',  // Links without href (inert)
    'code', 'pre', 'blockquote',
  ]);
  
  // DISALLOWED tags (remove with content)
  const REMOVE_TAGS = new Set([
    'script', 'style', 'svg', 'math',
    'object', 'embed', 'iframe', 'frame', 'frameset',
    'form', 'input', 'button', 'select', 'textarea',
    'link', 'meta', 'base',
    'img', 'audio', 'video', 'source', 'track',
    'picture', 'canvas', 'map', 'area',
  ]);
  
  // Remove disallowed tags entirely
  for (const tag of REMOVE_TAGS) {
    sanitized = sanitized.replace(new RegExp(`<${tag}\\b[^>]*>[\\s\\S]*?</${tag}>`, 'gi'), '');
    sanitized = sanitized.replace(new RegExp(`<${tag}\\b[^>]*/?>`, 'gi'), '');
  }
  
  // Remove non-allowlisted tags (keep content)
  // Match tag names with letters, numbers, and hyphens (for custom elements)
  sanitized = sanitized.replace(/<([a-zA-Z][a-zA-Z0-9-]*)([^>]*)>/gi, (match, tagName, attrs) => {
    const tag = tagName.toLowerCase();
    if (ALLOWED_TAGS.has(tag)) {
      // Extract only class and id attributes, rebuild from scratch
      const classMatch = attrs.match(/\s+class\s*=\s*(["'])([^"']*)\1/i);
      const idMatch = attrs.match(/\s+id\s*=\s*(["'])([^"']*)\1/i);
      
      // HTML-escape function for attribute values
      const escapeHtml = (str: string): string => {
        return str
          .replace(/&/g, '&amp;')
          .replace(/"/g, '&quot;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
      };
      
      let safeAttrs = '';
      if (classMatch) {
        safeAttrs += ` class="${escapeHtml(classMatch[2])}"`;
      }
      if (idMatch) {
        safeAttrs += ` id="${escapeHtml(idMatch[2])}"`;
      }
      return `<${tag}${safeAttrs}>`;
    }
    return '';
  });
  
  // Remove closing tags for non-allowlisted elements
  sanitized = sanitized.replace(/<\/([a-zA-Z][a-zA-Z0-9-]*)>/gi, (match, tagName) => {
    const tag = tagName.toLowerCase();
    if (ALLOWED_TAGS.has(tag)) {
      return match;
    }
    return '';
  });
  
  // Strip event handlers (belt and suspenders)
  sanitized = sanitized.replace(/\s+on\w+\s*=\s*(["'][^"']*["']|[^\s>]*)/gi, '');
  
  // Strip any remaining href/src attributes (should be gone by now)
  sanitized = sanitized.replace(/\s+(href|src)\s*=\s*(["'][^"']*["']|[^\s>]*)/gi, '');
  
  // Strip style attributes
  sanitized = sanitized.replace(/\s+style\s*=\s*(["'][^"']*["']|[^\s>]*)/gi, '');
  
  return sanitized;
}
