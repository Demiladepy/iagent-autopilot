/**
 * iAgent Autopilot UI taxonomy — aligned with https://component.gallery/
 *
 * Primitives live in @/components/ui (shadcn + Radix).
 * Composed patterns live in @/components/sentinel.
 */

export const GALLERY = {
  /** Vertical stack of headings that toggle further information */
  accordion: {
    gallery: "https://component.gallery/components/accordion/",
    aliases: ["Disclosure", "Collapsible", "Details"],
    primitive: "Accordion",
    sentinel: "DecisionDisclosure",
  },
  /** Page-level messages (errors, warnings, status) */
  alert: {
    gallery: "https://component.gallery/components/alert/",
    aliases: ["Banner", "Notice", "Callout"],
    primitive: "Alert",
    sentinel: "ConnectionAlert",
  },
  /** Small status labels */
  badge: {
    gallery: "https://component.gallery/components/badge/",
    aliases: ["Tag", "Chip", "Label"],
    primitive: "Badge",
    sentinel: "StatusBadge",
  },
  /** Primary actions */
  button: {
    gallery: "https://component.gallery/components/button/",
    primitive: "Button",
    sentinel: "ActionButton",
  },
  /** Grouped content surfaces */
  card: {
    gallery: "https://component.gallery/components/card/",
    primitive: "Card",
    sentinel: "PanelCard",
  },
  /** Modal overlays for confirmation / forms */
  dialog: {
    gallery: "https://component.gallery/components/dialog/",
    aliases: ["Modal"],
    primitive: "Dialog",
    sentinel: "ConfirmDialog",
  },
  /** Single-line text entry */
  textField: {
    gallery: "https://component.gallery/components/text-field/",
    aliases: ["Input", "Text input"],
    primitive: "Input",
    sentinel: "FormField",
  },
  /** Multi-line text entry */
  textarea: {
    gallery: "https://component.gallery/components/text-area/",
    primitive: "Textarea",
    sentinel: "StrategyTextarea",
  },
  /** Visual separation */
  separator: {
    gallery: "https://component.gallery/components/separator/",
    aliases: ["Divider"],
    primitive: "Separator",
  },
  /** Constrained scroll regions */
  scrollArea: {
    gallery: "https://component.gallery/components/scroll-area/",
    primitive: "ScrollArea",
    sentinel: "FeedScrollArea",
  },
  /** Completion / confidence visualization */
  progress: {
    gallery: "https://component.gallery/components/progress-indicator/",
    aliases: ["Meter", "Progress bar"],
    primitive: "Progress",
    sentinel: "ConfidenceMeter",
  },
  /** Transient feedback */
  notification: {
    gallery: "https://component.gallery/components/notification/",
    aliases: ["Toast", "Snackbar"],
    primitive: "Sonner",
    sentinel: "Toast",
  },
  /** Ordered items (events, balances) */
  list: {
    gallery: "https://component.gallery/components/list/",
    sentinel: "DataList",
  },
  /** Chronological pipeline (decision chain) */
  timeline: {
    gallery: "https://component.gallery/components/timeline/",
    sentinel: "DecisionTimeline",
  },
  /** Live / idle / error dots */
  statusIndicator: {
    gallery: "https://component.gallery/components/status-indicator/",
    aliases: ["Status", "Presence"],
    sentinel: "AgentStatusIndicator",
  },
} as const;

export type GalleryComponentId = keyof typeof GALLERY;
