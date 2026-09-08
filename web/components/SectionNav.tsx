"use client";

const SECTIONS = [
  { id: "how", label: "How it works" },
  { id: "enforcement", label: "Enforcement" },
  { id: "proof", label: "Proof" },
  { id: "performance", label: "Performance" },
  { id: "agent", label: "Agent skill" },
];

export default function SectionNav() {
  return (
    <div className="nav-links">
      {SECTIONS.map((s) => (
        <button
          key={s.id}
          type="button"
          className="nav-scroll"
          onClick={() =>
            document
              .getElementById(s.id)
              ?.scrollIntoView({ behavior: "smooth", block: "start" })
          }
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}
