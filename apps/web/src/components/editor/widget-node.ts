import { Node, mergeAttributes, VueNodeViewRenderer } from "@tiptap/vue-3";
import type { Ref } from "vue";
import WidgetNodeView from "./WidgetNodeView.vue";
import type { WidgetContext } from "./widget-context";

export interface WidgetNodeOptions {
  // Reactive runtime context (placements, widget resolver, callbacks). Passed in
  // by SlideCanvas via `.configure({ context })`. Delivered through the extension
  // options — not Vue `provide/inject` — because the NodeView always receives
  // `props.extension` synchronously, whereas inject across the TipTap NodeView
  // boundary depends on EditorContent having forwarded its app context first
  // (a mount-order race that can leave the widget stuck on its loading stub).
  context: Ref<WidgetContext> | null;
}

// A widget placement in the document. It is an atomic block node: it has no
// editable content, is not selectable as text, and cannot be split or merged
// into — so a stray keystroke can never delete it (the original Finding #2).
// Removal goes exclusively through the chrome's Remove button. The node carries
// only the `placementId`; the live widget data (resolved Widget body, props,
// callbacks) reaches the NodeView through the reactive `context` option.
export const WidgetNode = Node.create<WidgetNodeOptions>({
  name: "widget",
  group: "block",
  atom: true,
  selectable: false,
  draggable: false,

  addOptions() {
    return { context: null };
  },

  addAttributes() {
    return {
      placementId: {
        default: "",
        parseHTML: (el) => el.getAttribute("data-widget-id") || "",
        renderHTML: (attrs) => ({ "data-widget-id": attrs.placementId }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-block="widget"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-block": "widget" })];
  },

  addNodeView() {
    return VueNodeViewRenderer(WidgetNodeView);
  },
});
