// script.js - front-end behavior with image fallback, history, and robust generate

// --- small helpers ---
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const HISTORY_KEY = "sr_recipe_history_v1"; // localStorage key
const MAX_HISTORY = 12;

// toast
function toast(msg) {
  const el = document.createElement("div");
  el.textContent = msg;
  Object.assign(el.style, {
    position: "fixed",
    left: "50%",
    bottom: "28px",
    transform: "translateX(-50%)",
    background: "rgba(0,0,0,0.75)",
    color: "#fff",
    padding: "10px 14px",
    borderRadius: "10px",
    zIndex: 9999,
  });
  document.body.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity .4s";
    el.style.opacity = "0";
  }, 1400);
  setTimeout(() => el.remove(), 2000);
}

// read/write history (simple array of {query, diet, results})
function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    return JSON.parse(raw);
  } catch (e) {
    return [];
  }
}
function saveHistoryEntry(query, diet, results) {
  const hist = loadHistory();
  const entry = { id: Date.now(), query, diet, results };
  hist.unshift(entry);
  if (hist.length > MAX_HISTORY) hist.splice(MAX_HISTORY);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(hist));
  renderHistory();
}
function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
}
function renderHistory() {
  const list = $("#historyList");
  if (!list) return;
  list.innerHTML = "";
  const hist = loadHistory();
  if (!hist.length) {
    list.innerHTML =
      '<div class="small" style="color:var(--muted)">No history yet — generate recipes to build history.</div>';
    return;
  }
  hist.forEach((item) => {
    const btn = document.createElement("div");
    btn.className = "small";
    btn.style.padding = "8px";
    btn.style.border = "1px solid var(--border)";
    btn.style.borderRadius = "8px";
    btn.style.cursor = "pointer";
    btn.textContent = `${item.query}${item.diet ? " • " + item.diet : ""}`;
    btn.title = "Click to view results";
    btn.addEventListener("click", () => {
      // render results directly
      renderResults(item.results);
      // also populate the inputs
      const ing = $("#ingredients");
      if (ing) ing.value = item.query;
      const diet = $("#diet");
      if (diet) diet.value = item.diet || "";
    });
    list.appendChild(btn);
  });
}

// image fallback helper: returns unsplash URL for title
function unsplashFallback(title) {
  const q = encodeURIComponent(
    (title || "food dish").split(" ").slice(0, 3).join(" ")
  );
  return `https://source.unsplash.com/800x600/?${q},food`;
}

// Detect JSON content-type
function isJsonResponse(headers) {
  const ct = headers.get("content-type") || "";
  return ct.includes("application/json") || ct.includes("json");
}

// Generate recipes (main)
async function generateRecipes() {
  console.clear();
  const ingredientsEl = $("#ingredients");
  const dietEl = $("#diet");
  const results = $("#results");
  const loader = $("#loader");

  if (!ingredientsEl || !results) {
    toast("UI elements missing");
    return;
  }
  const pantry = ingredientsEl.value.trim();
  const diet = dietEl ? dietEl.value : "";

  if (!pantry) {
    toast("Please enter at least one ingredient.");
    return;
  }

  results.innerHTML = "";
  if (loader) loader.style.display = "block";

  try {
    const resp = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ pantry, diet }),
    });

    if (!resp.ok) {
      const txt = await resp.text();
      console.error("Non-OK response", resp.status, txt);
      if (loader) loader.style.display = "none";
      toast("Server error — check console");
      return;
    }

    // handle non-json (e.g., login HTML)
    if (!isJsonResponse(resp.headers)) {
      const text = await resp.text();
      console.warn("Non-JSON response", text.slice(0, 300));
      if (loader) loader.style.display = "none";
      if (text.toLowerCase().includes("login")) {
        toast("Session expired — redirecting to login");
        setTimeout(() => (window.location.href = "/login"), 800);
        return;
      }
      toast("Unexpected server response");
      return;
    }

    const data = await resp.json();
    console.log("generate response", data);
    if (loader) loader.style.display = "none";

    // Determine array of recipe objects
    let arr = [];
    if (Array.isArray(data)) arr = data;
    else if (Array.isArray(data.recipes)) arr = data.recipes;
    else if (Array.isArray(data.results)) arr = data.results;
    else if (data.recipe) arr = [data];
    else {
      // if object keyed by numbers or single recipe object
      if (typeof data === "object") {
        // attempt to extract array-like entries
        const vals = Object.values(data).filter(
          (v) => v && (v.title || v.recipes || v.link)
        );
        if (vals.length) arr = vals;
        else arr = [data];
      }
    }

    if (!arr || arr.length === 0) {
      results.innerHTML = `<div class="panel"><p>No recipes returned.</p></div>`;
      return;
    }

    // Render and save to history
    renderResults(arr);
    try {
      saveHistoryEntry(pantry, diet, arr);
    } catch (e) {
      console.warn("history save failed", e);
    }
  } catch (err) {
    console.error("Generate error", err);
    if (loader) loader.style.display = "none";
    toast("Network error. Check server.");
  }
}

// ------------------ REPLACE renderResults HERE (robust, preloading images) ------------------
// ------------------ renderResults with default local image ------------------
async function renderResults(arr) {
  const grid = $("#results");
  if (!grid) return;
  grid.innerHTML = "";

  const DEFAULT_IMG = "/static/images/default_food.jpg"; // make sure you have this image in static/images/

  // take up to 6 results
  const slice = (Array.isArray(arr) ? arr : []).slice(0, 6);

  slice.forEach((r) => {
    const title = r.title || (typeof r === "string" ? r : "Recipe");
    const instructions = (r.instructions || r.summary || "").replace(
      /<\/?[^>]+(>|$)/g,
      ""
    );
    const link = r.link && r.link !== "#" ? r.link : null;

    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <img src="${DEFAULT_IMG}" alt="${escapeHtml(title)}" loading="lazy">
      <div class="body">
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(truncate(instructions, 220))}</p>
        <div class="actions">
          <button class="action-btn save-btn">❤️ Save</button>
          <button class="action-btn speak-btn">🔊 Read</button>
          <a class="link open-btn" target="_blank">${
            link ? "Open" : "Search"
          }</a>
        </div>
      </div>
    `;

    // Save handler
    card.querySelector(".save-btn").addEventListener("click", async () => {
      try {
        await fetch("/favorite", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title,
            link: link || "#",
            image: DEFAULT_IMG,
          }),
        });
        toast("Saved to favorites ❤️");
      } catch (e) {
        console.error(e);
        toast("Save failed");
      }
    });

    // Speak handler
    card.querySelector(".speak-btn").addEventListener("click", () => {
      if (!("speechSynthesis" in window)) {
        toast("TTS not supported");
        return;
      }
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(`${title}. ${instructions || ""}`);
      u.lang = "en-US";
      u.rate = 1.0;
      u.pitch = 1.05;
      window.speechSynthesis.speak(u);
    });

    // Open handler
    const openBtn = card.querySelector(".open-btn");
    openBtn.addEventListener("click", () => {
      const targetUrl =
        link ||
        `https://www.google.com/search?q=${encodeURIComponent(
          title + " recipe"
        )}`;
      window.open(targetUrl, "_blank");
    });

    grid.appendChild(card);
  });
}
// ------------------ end renderResults update ------------------

// small helpers
function truncate(s, n) {
  s = s || "";
  return s.length > n ? s.slice(0, n) + "..." : s;
}
function escapeHtml(s) {
  if (!s) return "";
  return s.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[
        c
      ])
  );
}

// Init events
window.addEventListener("load", () => {
  const gen = $("#generateBtn");
  if (gen) gen.addEventListener("click", generateRecipes);
  const clearBtn = $("#clearHistory");
  if (clearBtn)
    clearBtn.addEventListener("click", () => {
      clearHistory();
      toast("History cleared");
    });

  renderHistory();
});
