async function erpAskAI() {
  const form = document.getElementById("ai-form");
  const output = document.getElementById("ai-result");
  if (!form || !output) return;

  const prompt = form.querySelector("textarea[name='prompt']").value.trim();
  if (!prompt) {
    output.textContent = "Type a prompt first.";
    return;
  }

  output.textContent = "Thinking...";

  try {
    const response = await fetch("/api/v1/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
      credentials: "same-origin",
    });

    const json = await response.json();
    output.textContent = json?.data?.assistant_response || json?.error?.message || "No response";
  } catch (error) {
    output.textContent = `Error: ${error.message}`;
  }
}
