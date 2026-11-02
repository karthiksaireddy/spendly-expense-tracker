// main.js — small UX helpers for Spendly.

// Confirm before submitting any form that opts in via [data-confirm].
document.addEventListener('submit', (event) => {
  const form = event.target;
  if (form.matches('form[data-confirm]')) {
    const message = form.getAttribute('data-confirm');
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  }
});
