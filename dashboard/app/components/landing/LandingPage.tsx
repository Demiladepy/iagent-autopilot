"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { HOW_IT_WORKS, PLATFORM_FEATURES } from "@/lib/brand-content";
import { IntegrationStrip } from "./IntegrationStrip";
import { MetricsGrid } from "./MetricsGrid";
import { SkillsShowcase } from "./SkillsShowcase";
import { WorkflowMockup } from "./WorkflowMockup";
import { Logo } from "@/components/Logo";

function ScrollReveal({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) setVisible(true);
      },
      { threshold: 0.1, rootMargin: "0px 0px -6% 0px" }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ease-out ${
        visible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function LandingPage() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 32);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="landing-root min-h-screen bg-black text-neutral-200">
      <header
        className={`fixed inset-x-0 top-0 z-50 transition-all duration-300 ${
          scrolled
            ? "border-b border-white/[0.06] bg-black/85 backdrop-blur-xl"
            : "bg-transparent"
        }`}
      >
        <div className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-4 md:px-10">
          <Link href="/" className="transition-opacity hover:opacity-90">
            <Logo size={32} showLabel />
          </Link>
          <nav className="flex items-center gap-4 text-[10px] uppercase tracking-[0.18em]">
            <a href="#platform" className="hidden text-neutral-500 transition-colors hover:text-white sm:inline">
              Platform
            </a>
            <a href="#how" className="hidden text-neutral-500 transition-colors hover:text-white sm:inline">
              How it works
            </a>
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-1.5 bg-white px-4 py-2 font-medium text-black transition-opacity hover:opacity-90"
            >
              Launch workbench
              <ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero — ai.work pattern: headline + product mockup */}
      <section className="relative overflow-hidden pt-28 pb-20 md:pt-36 md:pb-28">
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_70%_60%_at_50%_-10%,rgba(16,185,129,0.12),transparent_55%)]"
          aria-hidden
        />
        <div className="relative z-10 mx-auto max-w-[1400px] px-6 md:px-10">
          <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-emerald-500/80">
            Introducing Autopilot
          </p>
          <h1 className="mt-6 max-w-4xl text-[clamp(2.25rem,6vw,4.25rem)] font-semibold leading-[1.08] tracking-tight text-white">
            The first AI Worker for{" "}
            <span className="text-neutral-500">autonomous Injective trading</span>
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-neutral-400 md:text-lg">
            Five agents handle surveillance, proposals, risk, execution, and audit — so your desk moves faster
            with hard limits and a receipt for every decision.
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 bg-white px-6 py-3 text-sm font-medium text-black"
            >
              Launch workbench
              <ArrowUpRight className="h-4 w-4" />
            </Link>
            <a
              href="https://github.com/InjectiveLabs/mcp-server"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 border border-white/15 px-6 py-3 text-sm text-white transition-colors hover:border-white/30"
            >
              Injective MCP
              <ArrowUpRight className="h-4 w-4" />
            </a>
          </div>

          <div className="mt-16 md:mt-20">
            <WorkflowMockup />
          </div>
        </div>
      </section>

      <IntegrationStrip />

      <SkillsShowcase />
      <MetricsGrid />

      {/* How it works */}
      <section id="how" className="border-t border-white/10 px-6 py-24 md:px-10 md:py-32">
        <div className="mx-auto max-w-[1400px]">
          <ScrollReveal>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-neutral-600">04 · How it works</p>
            <h2 className="landing-display mt-4 text-[clamp(2rem,5vw,3.25rem)] font-light text-white">
              AI that learns from real trading work
            </h2>
            <div className="mt-14 grid gap-10 md:grid-cols-3">
              {HOW_IT_WORKS.map((item) => (
                <div key={item.label} className="workbench-card rounded-2xl p-6">
                  <span className="font-mono text-xs text-neutral-600">{item.label}</span>
                  <h3 className="mt-4 text-lg font-medium text-white">{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-neutral-400">{item.body}</p>
                </div>
              ))}
            </div>
          </ScrollReveal>
        </div>
      </section>

      {/* Platform features */}
      <section id="platform" className="border-t border-white/10 bg-neutral-950/40 px-6 py-24 md:px-10 md:py-32">
        <div className="mx-auto max-w-[1400px]">
          <ScrollReveal>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-neutral-600">05 · Platform</p>
            <h2 className="landing-display mt-4 text-[clamp(2rem,5vw,3.25rem)] font-light text-white">
              Powered by multi-agent orchestration
            </h2>
            <p className="mt-4 max-w-2xl text-neutral-400">
              Built for hackathon demos and production guardrails — deploy on Render + Vercel without Docker.
            </p>
            <div className="mt-12 grid gap-6 md:grid-cols-3">
              {PLATFORM_FEATURES.map((f) => (
                <div
                  key={f.title}
                  className="rounded-2xl border border-white/10 bg-black/40 p-6 transition-colors hover:border-white/20"
                >
                  <h3 className="text-base font-medium text-white">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-neutral-400">{f.body}</p>
                </div>
              ))}
            </div>
          </ScrollReveal>
        </div>
      </section>

      {/* Manifesto strip */}
      <section className="border-t border-white/10 px-6 py-24 md:px-10">
        <div className="mx-auto max-w-[1400px]">
          <ScrollReveal>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-neutral-600">01 · Manifesto</p>
            <h2 className="landing-display mt-4 max-w-3xl text-[clamp(2rem,5vw,3.5rem)] font-light leading-tight text-white">
              Capital with conviction — on official Injective MCP
            </h2>
            <p className="mt-6 max-w-2xl text-neutral-400 leading-relaxed">
              No parallel SDK. Every chain interaction flows through the Injective MCP Server. Architectural
              enforcement: only Executor submits writes. Risk, kill switch, and dry-run keep autonomy safe.
            </p>
          </ScrollReveal>
        </div>
      </section>

      <footer className="border-t border-white/10 px-6 py-20 md:px-10">
        <div className="mx-auto flex max-w-[1400px] flex-col items-start justify-between gap-8 md:flex-row md:items-end">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-neutral-600">
              Injective Solo AI Builder Sprint · May 2026
            </p>
            <p className="mt-4 text-2xl font-semibold tracking-tight text-white md:text-3xl">
              Onboard Autopilot. Watch one trade type live.
            </p>
          </div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 bg-white px-8 py-4 text-sm font-medium text-black"
          >
            Launch workbench
            <ArrowUpRight className="h-4 w-4" />
          </Link>
        </div>
      </footer>
    </div>
  );
}
