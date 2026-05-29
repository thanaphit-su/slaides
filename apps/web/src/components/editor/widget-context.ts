import type { InjectionKey, Ref } from "vue";
import type { SlideWidgetEmbed, Widget } from "@/api/types";

// Runtime data the widget NodeView needs but the document does NOT persist:
// the live placement list, a widget-body resolver, the adjust/remove callbacks,
// and a `rev` that bumps when a widget body must remount (AI apply / props
// save). SlideCanvas provides this; WidgetNodeView injects it. Kept reactive
// (a ref) so a placement/rev change repaints only the widget node views — never
// the editable text around them.
export interface WidgetContext {
  placements: SlideWidgetEmbed[];
  getWidget?: (id: string) => Widget | null;
  onAdjust?: (placement: SlideWidgetEmbed) => void;
  onRemove?: (placement: SlideWidgetEmbed) => void;
  rev: number;
  /** True when the slide is a single widget block — fill the canvas. */
  fill: boolean;
}

export const WIDGET_CONTEXT: InjectionKey<Ref<WidgetContext>> = Symbol("slaides-widget-context");
