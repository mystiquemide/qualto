"use client";

import { useEffect, useRef } from "react";

const SECTIONS: { group: string; items: { id: string; label: string }[] }[] = [
  {
    group: "Start",
    items: [
      { id: "install", label: "Install" },
      { id: "quickstart", label: "Quickstart" },
      { id: "prereq", label: "Prerequisites" },
    ],
  },
  {
    group: "Concepts",
    items: [
      { id: "claim", label: "The claim contract" },
      { id: "binding", label: "Claim binding" },
      { id: "verdicts", label: "Verdicts" },
      { id: "sessions", label: "Session states" },
    ],
  },
  {
    group: "Reference",
    items: [
      { id: "cli", label: "CLI reference" },
      { id: "receipts", label: "Receipt events" },
      { id: "exitcodes", label: "Exit codes" },
    ],
  },
  {
    group: "Trust",
    items: [
      { id: "verify", label: "Verification" },
      { id: "security", label: "Security model" },
      { id: "skill", label: "Agent skill" },
      { id: "limits", label: "Limits" },
    ],
  },
];

export default function DocsNav() {
  const refs = useRef<Map<string, HTMLElement>>(new Map());

  useEffect(() => {
    const links = Array.from(document.querySelectorAll<HTMLAnchorElement>(
      "aside a[href^='#']"
    ));
    const setActive = (id: string) => {
      links.forEach((a) => a.classList.remove("here"));
      links
        .filter((a) => a.getAttribute("href") === `#${id}`)
        .forEach((a) => a.classList.add("here"));
    };
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(e.target.id);
      },
      { rootMargin: "-20% 0px -70% 0px" }
    );
    document
      .querySelectorAll<HTMLElement>("main section[id]")
      .forEach((s) => observer.observe(s));
    return () => observer.disconnect();
  }, []);

  return (
    <aside aria-label="Documentation navigation">
      {SECTIONS.map((g) => (
        <div key={g.group}>
          <div className="group">{g.group}</div>
          {g.items.map((item) => (
            <a key={item.id} href={`#${item.id}`}>
              {item.label}
            </a>
          ))}
        </div>
      ))}
    </aside>
  );
}
