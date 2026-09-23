/* QuantVenue — small progressive enhancements (no framework) */

// Mobile navigation toggle
document.addEventListener("click", (e) => {
  const toggle = e.target.closest(".navtoggle");
  if (!toggle) return;
  const links = document.querySelector(".navlinks");
  if (!links) return;
  const open = links.classList.toggle("open");
  toggle.setAttribute("aria-expanded", open ? "true" : "false");
});

// Close the mobile menu after choosing a link
document.addEventListener("click", (e) => {
  if (!e.target.closest(".navlinks a")) return;
  const links = document.querySelector(".navlinks");
  if (links) links.classList.remove("open");
});

// Confirmation guard for destructive forms (data-confirm="...")
document.addEventListener("submit", (e) => {
  const form = e.target;
  if (form.dataset && form.dataset.confirm && !window.confirm(form.dataset.confirm)) {
    e.preventDefault();
  }
});
