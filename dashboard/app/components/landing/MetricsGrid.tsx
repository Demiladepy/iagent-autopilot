import { ROI_METRICS } from "@/lib/brand-content";

export function MetricsGrid() {
  return (
    <section className="border-t border-white/10 bg-black px-6 py-24 md:px-10 md:py-32">
      <div className="mx-auto max-w-[1400px]">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-neutral-600">03 · Outcomes</p>
        <h2 className="landing-display mt-4 text-[clamp(2rem,5vw,3.5rem)] font-light text-white">
          A new standard for autonomous trading ops
        </h2>
        <div className="mt-14 grid gap-6 md:grid-cols-3">
          {ROI_METRICS.map((m) => (
            <div
              key={m.title}
              className="workbench-card rounded-2xl p-8"
            >
              <p className="landing-display text-5xl font-light text-white md:text-6xl">
                {m.value}
                <span className="text-2xl text-neutral-500">{m.suffix}</span>
              </p>
              <h3 className="mt-6 text-lg font-medium text-white">{m.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-neutral-400">{m.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
