/**
 * CareNest Minimal Vanilla JS for Accessibility & UI Comfort.
 * No heavy frameworks.
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Accessibility: Large Text Mode Persistence
  const textToggleBtn = document.getElementById("toggle-text-size");
  if (textToggleBtn) {
    const isLarge = localStorage.getItem("carenest_large_text") === "true";
    if (isLarge) {
      document.body.classList.add("text-large");
      textToggleBtn.setAttribute("aria-pressed", "true");
    }

    textToggleBtn.addEventListener("click", () => {
      const active = document.body.classList.toggle("text-large");
      localStorage.setItem("carenest_large_text", active);
      textToggleBtn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  // 2. Accessibility: High Contrast Mode Persistence
  const contrastToggleBtn = document.getElementById("toggle-contrast");
  if (contrastToggleBtn) {
    const isHighContrast = localStorage.getItem("carenest_high_contrast") === "true";
    if (isHighContrast) {
      document.body.classList.add("high-contrast");
      contrastToggleBtn.setAttribute("aria-pressed", "true");
    }

    contrastToggleBtn.addEventListener("click", () => {
      const active = document.body.classList.toggle("high-contrast");
      localStorage.setItem("carenest_high_contrast", active);
      contrastToggleBtn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  // 3. Confirm Dangerous Actions (Delete medication, regenerate passcodes)
  const dangerForms = document.querySelectorAll("form[data-confirm]");
  dangerForms.forEach((form) => {
    form.addEventListener("submit", (e) => {
      const message = form.getAttribute("data-confirm") || "Are you sure you want to proceed?";
      if (!window.confirm(message)) {
        e.preventDefault();
      }
    });
  });

  // 4. Keyboard focus enhancements
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const dismissable = document.querySelector(".alert");
      if (dismissable) {
        dismissable.style.display = "none";
      }
    }
  });
});
