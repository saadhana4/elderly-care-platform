/**
 * CareNest Minimal Vanilla JS for Accessibility & UI Comfort.
 * - WCAG 2.2 AA/AAA screen reader live announcements
 * - Persistent high contrast & large text toggles
 * - Browser speech synthesis "Read Aloud" for daily medication routine
 * - Visible keyboard focus & escape handlers
 */

// Helper to announce status messages to screen readers via aria-live
function announceStatus(message) {
  const announcer = document.getElementById("status-announcer");
  if (announcer && message) {
    announcer.textContent = "";
    // Brief timeout ensures assistive tech registers the DOM text change
    setTimeout(() => {
      announcer.textContent = message;
    }, 50);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // 1. Accessibility: Screen Reader Announcer on page load for alerts
  const existingAlert = document.querySelector(".alert");
  if (existingAlert) {
    const alertText = existingAlert.textContent.trim();
    if (alertText) {
      announceStatus(alertText);
    }
  }

  // 2. Accessibility: Large Text Mode Persistence
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
      announceStatus(active ? "Extra large text enabled." : "Standard text restored.");
    });
  }

  // 3. Accessibility: High Contrast Mode Persistence
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
      announceStatus(active ? "High contrast theme enabled." : "Standard theme restored.");
    });
  }

  // 4. Accessibility: Read Aloud Speech Synthesis for Today's Medication Routine
  const readAloudBtn = document.getElementById("btn-read-aloud");
  if (readAloudBtn) {
    if (!("speechSynthesis" in window)) {
      // Gracefully hide button if browser does not support Speech Synthesis API
      readAloudBtn.style.display = "none";
    } else {
      let isSpeaking = false;

      readAloudBtn.addEventListener("click", () => {
        if (isSpeaking || window.speechSynthesis.speaking) {
          window.speechSynthesis.cancel();
          isSpeaking = false;
          readAloudBtn.innerHTML = '<span aria-hidden="true">🔊</span> Read Aloud';
          readAloudBtn.setAttribute("aria-label", "Read today's medication routine aloud");
          announceStatus("Reading stopped.");
          return;
        }

        const doseCards = document.querySelectorAll(".dose-card");
        let textParts = [];

        // Patient identification
        const patientNameEl = document.querySelector(".user-ribbon-inner strong");
        const patientName = patientNameEl ? patientNameEl.parentElement.textContent.trim() : "Patient";
        textParts.push(`Here is the daily medication routine for ${patientName}.`);

        if (!doseCards.length) {
          textParts.push("There are no scheduled medications for today.");
        } else {
          textParts.push(`You have ${doseCards.length} scheduled doses today.`);
          doseCards.forEach((card, index) => {
            const time = card.querySelector(".dose-time")?.innerText.trim() || "";
            const name = card.querySelector(".dose-name")?.innerText.trim() || "";
            const dosage = card.querySelector(".dose-dosage")?.innerText.trim() || "";
            const statusBadge = card.querySelector(".dose-header div:last-child")?.innerText.trim() || "";
            textParts.push(`Dose number ${index + 1}: At ${time}, ${name}, dosage ${dosage}. Status is ${statusBadge}.`);
          });
        }

        const fullScript = textParts.join(" ");
        const utterance = new SpeechSynthesisUtterance(fullScript);
        utterance.rate = 0.9; // Slower, clearer cadence for elderly comprehension
        utterance.pitch = 1.0;

        utterance.onstart = () => {
          isSpeaking = true;
          readAloudBtn.innerHTML = '<span aria-hidden="true">⏹️</span> Stop Reading';
          readAloudBtn.setAttribute("aria-label", "Stop reading aloud");
          announceStatus("Now reading daily medication list aloud.");
        };

        utterance.onend = () => {
          isSpeaking = false;
          readAloudBtn.innerHTML = '<span aria-hidden="true">🔊</span> Read Aloud';
          readAloudBtn.setAttribute("aria-label", "Read today's medication routine aloud");
          announceStatus("Finished reading.");
        };

        utterance.onerror = () => {
          isSpeaking = false;
          readAloudBtn.innerHTML = '<span aria-hidden="true">🔊</span> Read Aloud';
          readAloudBtn.setAttribute("aria-label", "Read today's medication routine aloud");
        };

        window.speechSynthesis.speak(utterance);
      });
    }
  }

  // 5. Confirm Dangerous Actions (Delete medication, regenerate passcodes)
  const dangerForms = document.querySelectorAll("form[data-confirm]");
  dangerForms.forEach((form) => {
    form.addEventListener("submit", (e) => {
      const message = form.getAttribute("data-confirm") || "Are you sure you want to proceed?";
      if (!window.confirm(message)) {
        e.preventDefault();
      }
    });
  });

  // 6. Keyboard focus enhancements (Escape key dismisses alerts)
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const dismissable = document.querySelector(".alert");
      if (dismissable) {
        dismissable.style.display = "none";
        announceStatus("Alert dismissed.");
      }
    }
  });
});
