document.addEventListener("DOMContentLoaded", () => {
  const button = document.getElementById("print-button");
  if (button) button.addEventListener("click", () => window.print());
});
