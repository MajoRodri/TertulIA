export function initCustomSelects() {
  document.querySelectorAll("select").forEach(buildCustomSelect);
}

function buildCustomSelect(native) {
  if (native.dataset.cselInit) return;
  native.dataset.cselInit = "1";
  native.style.cssText = "position:absolute;width:1px;height:1px;overflow:hidden;opacity:0;pointer-events:none;";
  native.tabIndex = -1;

  const wrapper = document.createElement("div");
  wrapper.className = "csel";
  wrapper.setAttribute("role", "combobox");
  wrapper.setAttribute("aria-expanded", "false");
  wrapper.setAttribute("aria-haspopup", "listbox");

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "csel-trigger";
  trigger.setAttribute("aria-label", native.getAttribute("aria-label") || "");

  const triggerText = document.createElement("span");
  triggerText.className = "csel-trigger-text";

  const arrow = document.createElement("span");
  arrow.className = "csel-arrow";
  arrow.setAttribute("aria-hidden", "true");
  arrow.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;

  trigger.appendChild(triggerText);
  trigger.appendChild(arrow);

  const dropdown = document.createElement("div");
  dropdown.className = "csel-dropdown";
  dropdown.setAttribute("role", "listbox");

  let optionButtons = [];

  function buildOptions() {
    dropdown.innerHTML = "";
    optionButtons = [];
    const children = Array.from(native.children);

    children.forEach((child) => {
      if (child.tagName === "OPTGROUP") {
        const groupLabel = document.createElement("div");
        groupLabel.className = "csel-group-label";
        groupLabel.textContent = child.label;
        dropdown.appendChild(groupLabel);

        Array.from(child.children).forEach((opt) => {
          appendOptionButton(opt);
        });
      } else if (child.tagName === "OPTION") {
        appendOptionButton(child);
      }
    });
  }

  function appendOptionButton(opt) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "csel-option";
    if (!opt.value) btn.classList.add("csel-option--placeholder");
    btn.textContent = opt.textContent;
    btn.dataset.value = opt.value;
    btn.disabled = opt.disabled;
    btn.setAttribute("role", "option");
    if (opt.disabled) btn.setAttribute("aria-disabled", "true");

    btn.addEventListener("click", () => {
      native.value = btn.dataset.value;
      native.dispatchEvent(new Event("change", { bubbles: true }));
      syncTrigger();
      close();
    });

    dropdown.appendChild(btn);
    optionButtons.push(btn);
  }

  function syncTrigger() {
    const selected = native.options[native.selectedIndex];
    const text = selected ? selected.textContent.trim() : "";
    const isEmpty = !selected || selected.value === "";
    triggerText.textContent = text;
    triggerText.classList.toggle("csel-placeholder", isEmpty);
  }

  function open() {
    wrapper.classList.add("csel-open");
    wrapper.setAttribute("aria-expanded", "true");
    trigger.setAttribute("aria-expanded", "true");

    const currentVal = native.value;
    optionButtons.forEach((btn) => {
      const isSelected = btn.dataset.value === currentVal;
      btn.classList.toggle("csel-option--selected", isSelected);
      btn.setAttribute("aria-selected", String(isSelected));
    });

    requestAnimationFrame(() => {
      const sel = dropdown.querySelector(".csel-option--selected");
      if (sel) sel.scrollIntoView({ block: "nearest" });
    });

    document.addEventListener("click", onOutsideClick, { capture: true });
    document.addEventListener("keydown", onKeyDown, { capture: true });
  }

  function close() {
    wrapper.classList.remove("csel-open");
    wrapper.setAttribute("aria-expanded", "false");
    trigger.setAttribute("aria-expanded", "false");
    document.removeEventListener("click", onOutsideClick, { capture: true });
    document.removeEventListener("keydown", onKeyDown, { capture: true });
  }

  function onOutsideClick(e) {
    if (!wrapper.contains(e.target)) close();
  }

  function onKeyDown(e) {
    const navigable = optionButtons.filter(b => !b.disabled);
    const currentIdx = navigable.indexOf(
      optionButtons.find(b => b.classList.contains("csel-option--selected"))
    );

    if (e.key === "Escape") {
      e.preventDefault();
      close();
      trigger.focus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = navigable[Math.min(currentIdx + 1, navigable.length - 1)];
      next?.scrollIntoView({ block: "nearest" });
      next?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prev = navigable[Math.max(currentIdx - 1, 0)];
      prev?.scrollIntoView({ block: "nearest" });
      prev?.focus();
    } else if (e.key === "Tab") {
      close();
    }
  }

  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    if (wrapper.classList.contains("csel-open")) {
      close();
    } else {
      open();
    }
  });

  wrapper.appendChild(trigger);
  wrapper.appendChild(dropdown);
  native.insertAdjacentElement("afterend", wrapper);

  buildOptions();
  syncTrigger();
}
