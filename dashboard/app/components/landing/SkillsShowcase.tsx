"use client";

import { useEffect, useState } from "react";
import { AGENT_SKILLS } from "@/lib/brand-content";
import { cn } from "@/lib/utils";

export function SkillsShowcase() {
  const [active, setActive] = useState(0);
  const skill = AGENT_SKILLS[active];

  useEffect(() => {
    const t = setInterval(() => setActive((a) => (a + 1) % AGENT_SKILLS.length), 4500);
    return () => clearInterval(t);
  }, []);

  return (
    <section className="border-t border-white/10 px-6 py-24 md:px-10 md:py-32">
      <div className="mx-auto max-w-[1400px]">
        <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-neutral-600">02 · Skills</p>
        <h2 className="landing-display mt-4 max-w-3xl text-[clamp(2rem,5vw,3.5rem)] font-light leading-tight text-white">
          Skilled, pre-trained &amp; ready for Injective
        </h2>
        <p className="mt-4 max-w-xl text-neutral-400">
          Five specialized agents handle core trading work — surveillance through audit — with value visible in minutes on the live dashboard.
        </p>

        <div className="mt-12 grid gap-8 lg:grid-cols-[1fr_320px]">
          <article
            key={skill.num}
            className="workbench-mockup p-6 md:p-8 transition-opacity duration-500"
          >
            <p className="font-mono text-xs text-neutral-500">
              {active + 1} / {AGENT_SKILLS.length}
            </p>
            <p className="mt-2 text-[10px] font-semibold uppercase tracking-wider text-emerald-500/90">
              Skill
            </p>
            <h3 className="mt-2 text-2xl font-light text-white">{skill.title}</h3>
            <p className="mt-4 text-sm leading-relaxed text-neutral-400">{skill.body}</p>
            <span className="mt-6 inline-block rounded-full border border-white/10 px-3 py-1 font-mono text-xs text-neutral-300">
              {skill.tag}
            </span>
          </article>

          <div className="flex flex-col gap-2">
            {AGENT_SKILLS.map((s, i) => (
              <button
                key={s.num}
                type="button"
                onClick={() => setActive(i)}
                className={cn(
                  "rounded-xl border px-4 py-3 text-left transition-all",
                  i === active
                    ? "skill-card-active border-emerald-500/30"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20"
                )}
              >
                <span className="font-mono text-[10px] text-neutral-500">{s.num}</span>
                <p className="mt-1 text-sm font-medium text-white">{s.title}</p>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
