/**
 * Client-side parse-check for LLM-generated widget JS. Surfaces engine
 * SyntaxErrors so we can refuse to persist a draft that would silently
 * fail at iframe boot.
 *
 * The IIFE-as-string contract is fragile: any unterminated literal, any
 * unmatched brace, any multi-line single-quoted string and the whole
 * script throws at parse time. The audience can't tell — the button just
 * does nothing. Running the body through `new Function(body)` forces a
 * parse without execution and gives us the engine's error message, which
 * the chat-error chip in WidgetCollection.vue surfaces directly to the
 * user so they can re-iterate the prompt.
 */

export function validateDraftJs(js: string | null | undefined): string | null {
  const body = (js || "").trim();
  // Empty JS is legitimate — static / Quiet widgets often ship HTML+CSS only.
  if (!body) return null;
  try {
    // new Function(body) parses the source and constructs a function. It
    // does NOT execute the IIFE inside; that only happens when the
    // returned function is called, which we never do. A SyntaxError fires
    // synchronously from the constructor on a parse failure and includes
    // the engine's position token (e.g. "Unexpected token at line 174").
    // eslint-disable-next-line no-new, no-new-func
    new Function(body);
    return null;
  } catch (err) {
    if (err instanceof SyntaxError) {
      return `AI JS has a syntax error — re-iterate. ${err.message}`;
    }
    // Anything else (RangeError, ReferenceError from a custom Function
    // subclass, …) is not a parse-time signal. Don't gate the apply.
    return null;
  }
}
