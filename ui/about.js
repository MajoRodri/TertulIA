const TARGETS = [
  ".study-section .eyebrow",
  ".study-section h2",
  ".study-section .section-sub",
  ".study-block",
  ".study-pillar",
  ".curiosities-section .eyebrow",
  ".curiosities-section h2",
  ".curiosities-section .section-sub",
  ".curiosity-card",
];

const observer = new IntersectionObserver(
  (entries) => entries.forEach(e => e.target.classList.toggle("visible", e.isIntersecting)),
  { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
);

TARGETS.flatMap(sel => [...document.querySelectorAll(sel)]).forEach(el => {
  el.classList.add("reveal");
  if (el.matches(".study-block, .study-pillar, .curiosity-card, .curiosity-card--featured")) {
    const idx = [...el.parentElement.children].indexOf(el);
    el.style.transitionDelay = `${idx * 0.1}s`;
  }
  observer.observe(el);
});
