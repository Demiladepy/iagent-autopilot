import { INTEGRATIONS } from "@/lib/brand-content";

export function IntegrationStrip() {
  const row = [...INTEGRATIONS, ...INTEGRATIONS];

  return (
    <section className="border-y border-white/10 bg-neutral-950/80 py-8 overflow-hidden">
      <p className="mb-6 text-center font-mono text-[10px] uppercase tracking-[0.25em] text-neutral-600">
        Runs inside the stack you already trust
      </p>
      <div className="relative flex overflow-hidden">
        <div className="flex min-w-max animate-marquee gap-3 px-4">
          {row.map((name, i) => (
            <span key={`${name}-${i}`} className="integration-pill shrink-0">
              {name}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
