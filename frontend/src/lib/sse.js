import { getToken } from "@/lib/api";

/**
 * POST to an SSE endpoint and dispatch events as they arrive.
 * Handlers: onText(delta), onEvent(name, data). Resolves when the stream ends.
 */
export async function streamSSE(url, body, { signal, onText, onEvent } = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to reach RADHA");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const evt of events) {
      let name = "message";
      let data = "";
      for (const line of evt.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue; // keep-alive comments
      const parsed = JSON.parse(data);
      if (name === "error") throw new Error(parsed || "Stream error");
      if (name === "message") onText?.(parsed);
      else onEvent?.(name, parsed);
    }
  }
}
