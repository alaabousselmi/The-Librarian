const $ = (id) => document.getElementById(id);
let currentRequestId = null;

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderAnswer(text, citations) {
  const known = new Set(citations.map((c) => c.n));
  let html = window.marked ? marked.parse(text) : `<p>${escapeHtml(text)}</p>`;
  html = window.DOMPurify ? DOMPurify.sanitize(html) : html;
  // turn [1] / [1, 2] into links to the source list
  return html.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (m, nums) =>
    nums.split(",").map((n) => n.trim()).map((n) =>
      known.has(Number(n)) ? `<a class="cite" href="#src-${n}">[${n}]</a>` : `[${n}]`).join(""));
}

function renderSources(citations) {
  const ol = $("sources");
  ol.innerHTML = "";
  for (const c of citations) {
    const li = document.createElement("li");
    li.id = `src-${c.n}`;
    li.value = c.n;
    li.innerHTML = `<a href="${encodeURI(c.url)}" target="_blank" rel="noopener">${escapeHtml(c.title)}</a>
      <span class="tag ${c.source_type}">${c.source_type}</span>
      <blockquote>${escapeHtml(c.snippet)}${c.snippet.length >= 400 ? "…" : ""}</blockquote>`;
    ol.appendChild(li);
  }
  if (!citations.length) ol.innerHTML = "<li class='none'>No sources cited.</li>";
}

$("ask-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = $("question").value.trim();
  if (question.length < 3) return;
  const sources = [...document.querySelectorAll("input[name=src]:checked")].map((i) => i.value);
  $("ask-btn").disabled = true;
  $("ask-btn").textContent = "Searching…";
  $("error").hidden = true;
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, filters: sources.length < 3 ? { source_types: sources } : null }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
    currentRequestId = data.request_id;
    $("answer").innerHTML = renderAnswer(data.answer, data.citations);
    $("meta").textContent = `${(data.timings_ms.total_ms / 1000).toFixed(1)} s` +
      (data.abstained ? " · no confident answer found" : "");
    renderSources(data.citations);
    $("fb-status").textContent = "";
    $("fb-comment").value = "";
    $("result").hidden = false;
  } catch (err) {
    $("error").textContent = err.message;
    $("error").hidden = false;
  } finally {
    $("ask-btn").disabled = false;
    $("ask-btn").textContent = "Ask";
  }
});

document.querySelectorAll(".feedback button").forEach((btn) =>
  btn.addEventListener("click", async () => {
    if (!currentRequestId) return;
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: currentRequestId,
        rating: Number(btn.dataset.rating),
        comment: $("fb-comment").value.trim() || null,
      }),
    });
    $("fb-status").textContent = res.ok ? "Thanks — recorded." : "Could not save feedback.";
  }));

$("question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("ask-form").requestSubmit();
});
