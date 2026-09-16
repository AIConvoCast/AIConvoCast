const form = document.getElementById("contact-form");
const status = document.getElementById("form-status");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const button = form.querySelector('button[type="submit"]');
  if (button.disabled) return;
  button.disabled = true;
  status.hidden = false;
  status.textContent = "Sending your message...";
  try {
    const response = await fetch(form.action, {
      method: "POST", body: new FormData(form),
      headers: { Accept: "application/json" }, credentials: "omit",
    });
    if (!response.ok) throw new Error("Submission failed");
    form.hidden = true;
    status.textContent = "Thank you. Your message has been sent.";
    status.focus();
  } catch {
    status.textContent = "Your message could not be sent. Please try again, or email AIConvoCast@gmail.com.";
    button.disabled = false;
  }
});
