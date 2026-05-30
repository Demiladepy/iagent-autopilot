# UI components (Component Gallery + ai.work patterns)

Definitions follow [The Component Gallery](https://component.gallery/) for primitives and [ai.work (Henry)](https://www.ai.work/) for marketing/workbench chrome — numbered sections, skill cards, workflow mockup, human-in-the-loop dialogs.

## Layering

| Layer | Path | Role |
|-------|------|------|
| **Primitives** | `components/ui/` | shadcn + Radix building blocks |
| **Autopilot patterns** | `components/sentinel/` | Product-specific compositions |
| **App screens** | `app/components/` | Page layout wiring |
| **Registry** | `lib/component-registry.ts` | Gallery name → file mapping |

## Primitive → Gallery

| Primitive | Gallery component | Docs |
|-----------|-------------------|------|
| `Accordion` | Accordion / Disclosure | [accordion](https://component.gallery/components/accordion/) |
| `Alert` | Alert / Banner | [alert](https://component.gallery/components/alert/) |
| `Badge` | Badge / Tag | [badge](https://component.gallery/components/badge/) |
| `Button` | Button | [button](https://component.gallery/components/button/) |
| `Card` | Card | [card](https://component.gallery/components/card/) |
| `Dialog` | Dialog / Modal | [dialog](https://component.gallery/components/dialog/) |
| `Input` | Text field | [text-field](https://component.gallery/components/text-field/) |
| `Textarea` | Text area | [text-area](https://component.gallery/components/text-area/) |
| `Progress` | Progress indicator / Meter | [progress-indicator](https://component.gallery/components/progress-indicator/) |
| `ScrollArea` | Scroll area | [scroll-area](https://component.gallery/components/scroll-area/) |
| `Separator` | Separator / Divider | [separator](https://component.gallery/components/separator/) |
| Sonner (`Providers`) | Notification / Toast | [notification](https://component.gallery/components/notification/) |

## Autopilot pattern → Dashboard feature

| Autopilot export | Gallery pattern | Used in |
|-----------------|-----------------|---------|
| `DecisionDisclosure` | Accordion + Timeline | Decision feed — collapsible pipeline + raw JSON |
| `ConnectionAlert` | Alert (warning) | Offline / reconnect banner |
| `ConfidenceMeter` | Progress / Meter | Analyst confidence on decision cards |
| `AgentStatusIndicator` | Status indicator | Agent fleet status dot |
| `PanelCard` | Card | Strategy, portfolio, demo panels |
| `FeedScrollArea` | Scroll area | Decision timeline, event ticker |
| `DataList` | List | Positions, balances, events |

## App screen mapping

| Screen module | Primary gallery components |
|---------------|---------------------------|
| `DecisionFeed` | Timeline, Scroll area, Accordion |
| `DecisionCard` | Re-exports `DecisionDisclosure` |
| `AgentGrid` | Card, Status indicator |
| `KillSwitch` | Button, Dialog (confirm) |
| `StrategyEditor` | Text area, Text field, Dialog, Badge, Button |
| `PositionPanel` | Card, List, Separator, Badge |
| `EventTicker` | List, Scroll area |
| `DemoControls` | Button, Dialog |
| `AuditStream` | Card, Scroll area, Badge |
| `OfflineBanner` | Re-exports `ConnectionAlert` |
| `LandingPage` | — (marketing layout; editorial sections) |

## Accessibility notes (from Gallery guidance)

- **Accordion**: `aria-expanded` via Radix; one or multiple panels — we use `type="single"` per decision card with a nested item for raw JSON.
- **Alert**: `role="alert"` on `Alert` primitive for connection warnings.
- **Progress**: `role="meter"` with `aria-valuenow` on `ConfidenceMeter`.
- **Status**: `role="status"` + `aria-label` on agent dots.

## Adding a new UI piece

1. Find the pattern on [component.gallery](https://component.gallery/).
2. Add an entry to `lib/component-registry.ts`.
3. Prefer an existing `components/ui/*` primitive; compose in `components/sentinel/`.
4. Import from `@/components/sentinel` in app code — not raw markup in pages.
