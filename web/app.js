const log = document.getElementById("log");
const results = document.getElementById("results");
const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const langSelect = document.getElementById("lang");
const cancelBtn = document.getElementById("chat-cancel");
const history = [];
let chatAbortController = null;
const modeBadge = document.getElementById("mode-badge");

// --- Auth ---------------------------------------------------------
// Session lives in an httpOnly cookie set by the server - JS never sees
// the token, only whether we're logged in (via /api/auth/me) and as whom.
const CSRF_HEADERS = { "X-Requested-With": "XMLHttpRequest" };

let auth = null; // { username } | null - resolved from /api/auth/me on load
let currentPlan = null; // { lang, days: [...] } | null
let planBusy = false; // blocks overlapping plan mutations (swap/done/save/delete)
// Bumped on every clearAuth()/successful login. Every async plan call
// captures it before its await and checks it's unchanged after - a
// request started by a session that's since logged out (or been
// replaced by a different login) is discarded instead of applying its
// late-arriving result on top of whoever is signed in now.
let authGeneration = 0;

function clearAuth() {
  auth = null;
  currentPlan = null;
  authGeneration++;
  // Clear the plan DOM synchronously (not just via the async loadPlan() that
  // showView("plan") triggers later) - otherwise a different user logging
  // in on the same tab and opening "Mon planning" could briefly see the
  // previous user's plan still rendered while their own GET /api/plan is
  // still in flight.
  renderPlanView();
  updateAuthUI();
  showView("chat");
}

async function apiPlanFetch(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...CSRF_HEADERS, ...(options.headers || {}) },
  });
  if (res.status === 401) clearAuth();
  return res;
}

function updateAuthUI() {
  const loggedIn = !!auth;
  document.getElementById("auth-form").classList.toggle("hidden", loggedIn);
  document.getElementById("auth-logged").classList.toggle("hidden", !loggedIn);
  document.getElementById("view-nav").classList.toggle("hidden", !loggedIn);
  if (loggedIn) document.getElementById("auth-username-display").textContent = auth.username;
  // The chat assistant now requires a login (its API calls cost real
  // money) - hide the form and show an explanatory message instead.
  document.getElementById("chat-locked").classList.toggle("hidden", loggedIn);
  document.getElementById("chat-form").classList.toggle("hidden", !loggedIn);
}

async function doAuth(path) {
  const authError = document.getElementById("auth-error");
  authError.textContent = "";
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;
  if (!username || !password) return;
  const loginBtn = document.getElementById("auth-login-btn");
  const registerBtn = document.getElementById("auth-register-btn");
  loginBtn.disabled = true;
  registerBtn.disabled = true;
  try {
    const res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...CSRF_HEADERS },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      authError.textContent = data.detail || "Erreur";
      return;
    }
    auth = { username: data.username };
    authGeneration++;
    document.getElementById("auth-password").value = "";
    updateAuthUI();
  } catch (err) {
    authError.textContent = "Erreur réseau";
  } finally {
    loginBtn.disabled = false;
    registerBtn.disabled = false;
  }
}

document.getElementById("auth-form").addEventListener("submit", (e) => {
  e.preventDefault();
  doAuth("/api/auth/login");
});
document.getElementById("auth-register-btn").addEventListener("click", () => doAuth("/api/auth/register"));
document.getElementById("auth-logout-btn").addEventListener("click", async () => {
  try {
    await apiPlanFetch("/api/auth/logout", { method: "POST" });
  } catch (err) {
    // ignore - clearAuth still runs below, local session is cleared either way
  }
  clearAuth();
});

// --- View switching (chat vs. plan) --------------------------------
function showView(name) {
  document.getElementById("chat-view").classList.toggle("hidden", name !== "chat");
  document.getElementById("plan-view").classList.toggle("hidden", name !== "plan");
  document.getElementById("nav-chat").classList.toggle("active", name === "chat");
  document.getElementById("nav-plan").classList.toggle("active", name === "plan");
  if (name === "plan") loadPlan();
}

document.getElementById("nav-chat").addEventListener("click", () => showView("chat"));
document.getElementById("nav-plan").addEventListener("click", () => showView("plan"));

// --- Weekly plan ----------------------------------------------------
const WEEKDAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const WEEKDAY_LABELS = {
  fr: {
    monday: "Lundi", tuesday: "Mardi", wednesday: "Mercredi", thursday: "Jeudi",
    friday: "Vendredi", saturday: "Samedi", sunday: "Dimanche",
  },
  en: {
    monday: "Monday", tuesday: "Tuesday", wednesday: "Wednesday", thursday: "Thursday",
    friday: "Friday", saturday: "Saturday", sunday: "Sunday",
  },
};
const SUGGESTED_WEEKDAYS = {
  1: ["monday"],
  2: ["monday", "thursday"],
  3: ["monday", "wednesday", "friday"],
  4: ["monday", "tuesday", "thursday", "friday"],
  5: ["monday", "tuesday", "wednesday", "friday", "saturday"],
  6: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
};

function weekdayLabel(weekday, lang) {
  const labels = WEEKDAY_LABELS[lang] || WEEKDAY_LABELS.en;
  const unscheduledLabel = lang === "fr" ? "Non planifié" : "Unscheduled";
  if (!weekday) return unscheduledLabel;
  return labels[weekday] || unscheduledLabel;
}

async function loadPlan() {
  if (!auth) return;
  const generation = authGeneration;
  let plan;
  try {
    const res = await apiPlanFetch("/api/plan");
    plan = res.ok ? await res.json() : null;
  } catch (err) {
    plan = null;
  }
  // discard a response that arrived after the session that started this
  // request logged out or was replaced by a different login
  if (generation !== authGeneration) return;
  currentPlan = plan;
  renderPlanView();
}

// Builds the img + name/tags/meta block shared by every exercise card via
// DOM methods (textContent, not innerHTML) - exercise names/tags ultimately
// come from the dataset, but nothing here should trust that data enough to
// parse it as HTML.
function fillCardBody(body, exercise, meta) {
  const img = document.createElement("img");
  img.src = exercise.gif_url;
  img.alt = exercise.name;
  img.loading = "lazy";
  body.appendChild(img);

  const info = document.createElement("div");
  info.className = "info";

  const name = document.createElement("p");
  name.className = "name";
  name.textContent = exercise.name;
  info.appendChild(name);

  const tags = document.createElement("p");
  tags.className = "tags";
  tags.textContent = `${exercise.equipment.join(" + ")} · ${exercise.category} · ${exercise.target}`;
  info.appendChild(tags);

  if (meta) {
    const metaEl = document.createElement("p");
    metaEl.className = "meta";
    metaEl.textContent = meta;
    info.appendChild(metaEl);
  }

  body.appendChild(info);
}

function makePlanCard(item, dayIdx, lang, restLabel) {
  const card = document.createElement("div");
  card.className = "card";

  const body = document.createElement("button");
  body.type = "button";
  body.className = "card-body";
  const meta = `${item.sets} × ${item.reps} · ${restLabel} ${item.rest_seconds}s`;
  fillCardBody(body, item.exercise, meta);
  body.addEventListener("click", () => {
    cacheExercise(item.exercise, lang);
    openModal(item.exercise.id);
  });
  card.appendChild(body);

  const swapBtn = document.createElement("button");
  swapBtn.type = "button";
  swapBtn.className = "swap-btn";
  swapBtn.title = lang === "fr" ? "Remplacer" : "Swap";
  swapBtn.textContent = "⟲";
  swapBtn.disabled = planBusy;
  swapBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (planBusy) return;
    planBusy = true;
    const generation = authGeneration;
    let updated = null;
    try {
      const res = await apiPlanFetch("/api/plan/exercise/swap", {
        method: "POST",
        body: JSON.stringify({ day_index: dayIdx, exercise_id: item.exercise.id }),
      });
      if (res.ok) updated = await res.json();
    } catch (err) {
      // keep the previous plan state on error
    }
    planBusy = false;
    if (generation !== authGeneration) return; // session logged out/changed while this was in flight
    if (updated) currentPlan = updated;
    renderPlanView();
  });
  card.appendChild(swapBtn);

  const doneWrap = document.createElement("label");
  doneWrap.className = "done-checkbox-wrap";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = !!item.done;
  checkbox.disabled = planBusy;
  checkbox.addEventListener("change", async () => {
    if (planBusy) {
      checkbox.checked = item.done;
      return;
    }
    planBusy = true;
    const generation = authGeneration;
    let updated = null;
    try {
      const res = await apiPlanFetch("/api/plan/exercise/done", {
        method: "PATCH",
        body: JSON.stringify({ day_index: dayIdx, exercise_id: item.exercise.id, done: checkbox.checked }),
      });
      if (res.ok) updated = await res.json();
    } catch (err) {
      // keep the previous plan state on error
    }
    planBusy = false;
    if (generation !== authGeneration) return; // session logged out/changed while this was in flight
    if (updated) currentPlan = updated;
    renderPlanView();
  });
  doneWrap.appendChild(checkbox);
  doneWrap.appendChild(document.createTextNode(lang === "fr" ? " fait" : " done"));
  card.appendChild(doneWrap);

  return card;
}

function renderPlanView() {
  const container = document.getElementById("plan-content");
  container.innerHTML = "";
  const lang = currentPlan ? currentPlan.lang : langSelect.value;

  if (!currentPlan || !currentPlan.days.some((d) => d.exercises.length)) {
    const p = document.createElement("p");
    p.className = "plan-empty";
    p.textContent =
      lang === "fr"
        ? 'Aucun planning enregistré. Génère un programme dans le chat puis clique sur "Enregistrer dans mon planning".'
        : 'No saved plan yet. Generate a program in chat then click "Save to my plan".';
    container.appendChild(p);
    return;
  }

  const restLabel = lang === "fr" ? "repos" : "rest";
  const byWeekday = new Map(WEEKDAY_ORDER.map((w) => [w, []]));
  const unscheduled = [];
  currentPlan.days.forEach((day, dayIdx) => {
    const entry = { day, dayIdx };
    if (day.weekday && byWeekday.has(day.weekday)) byWeekday.get(day.weekday).push(entry);
    else unscheduled.push(entry);
  });
  const orderedGroups = WEEKDAY_ORDER.map((w) => byWeekday.get(w)).concat([unscheduled]);

  for (const entries of orderedGroups) {
    for (const { day, dayIdx } of entries) {
      if (!day.exercises.length) continue;
      const section = document.createElement("div");
      section.className = "plan-day";
      const h3 = document.createElement("h3");
      h3.textContent = `${weekdayLabel(day.weekday, lang)} — ${day.label}`;
      section.appendChild(h3);
      const grid = document.createElement("div");
      grid.className = "grid";
      day.exercises.forEach((item) => grid.appendChild(makePlanCard(item, dayIdx, lang, restLabel)));
      section.appendChild(grid);
      container.appendChild(section);
    }
  }

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.id = "plan-delete-btn";
  deleteBtn.textContent = lang === "fr" ? "Supprimer mon planning" : "Delete my plan";
  deleteBtn.disabled = planBusy;
  deleteBtn.addEventListener("click", async () => {
    if (planBusy) return;
    planBusy = true;
    const generation = authGeneration;
    let deleted = false;
    try {
      const res = await apiPlanFetch("/api/plan", { method: "DELETE" });
      deleted = res.ok;
    } catch (err) {
      // deleted stays false - plan re-renders from whatever currentPlan still holds
    }
    planBusy = false;
    if (generation !== authGeneration) return; // session logged out/changed while this was in flight
    if (deleted) currentPlan = null;
    renderPlanView();
  });
  container.appendChild(deleteBtn);
}

function renderSaveToPlanBar(program, lang) {
  if (!auth) return;
  const bar = document.createElement("div");
  bar.className = "save-plan-bar";

  const title = document.createElement("p");
  title.textContent = lang === "fr" ? "Enregistrer ce programme dans mon planning :" : "Save this program to my plan:";
  bar.appendChild(title);

  const suggestion = SUGGESTED_WEEKDAYS[program.days.length] || WEEKDAY_ORDER.slice(0, program.days.length);
  const selects = program.days.map((day, i) => {
    const row = document.createElement("div");
    row.className = "day-row";
    const label = document.createElement("span");
    label.textContent = day.label;
    row.appendChild(label);
    const select = document.createElement("select");
    const noneOpt = document.createElement("option");
    noneOpt.value = "";
    noneOpt.textContent = lang === "fr" ? "Non planifié" : "Unscheduled";
    select.appendChild(noneOpt);
    for (const weekday of WEEKDAY_ORDER) {
      const opt = document.createElement("option");
      opt.value = weekday;
      opt.textContent = weekdayLabel(weekday, lang);
      select.appendChild(opt);
    }
    select.value = suggestion[i] || "";
    row.appendChild(select);
    bar.appendChild(row);
    return select;
  });

  const errorEl = document.createElement("p");
  errorEl.className = "auth-error";
  bar.appendChild(errorEl);

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = lang === "fr" ? "Confirmer" : "Confirm";
  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    errorEl.textContent = "";
    const generation = authGeneration;
    const days = program.days.map((day, i) => ({
      weekday: selects[i].value || null,
      label: day.label,
      exercises: day.exercises.map((item) => ({
        exercise_id: item.exercise.id,
        sets: item.sets,
        reps: item.reps,
        rest_seconds: item.rest_seconds,
        done: false,
      })),
    }));
    try {
      const res = await apiPlanFetch("/api/plan", { method: "PUT", body: JSON.stringify({ lang, days }) });
      // session logged out/changed while this was in flight - drop the
      // result rather than switching the (now different, or logged-out)
      // session over to the plan view
      if (generation !== authGeneration) return;
      if (res.ok) {
        currentPlan = await res.json();
        showView("plan");
      } else {
        const body = await res.json().catch(() => ({}));
        errorEl.textContent = body.detail || (lang === "fr" ? "Échec de l'enregistrement." : "Failed to save.");
        saveBtn.disabled = false;
      }
    } catch (err) {
      errorEl.textContent = lang === "fr" ? "Erreur réseau." : "Network error.";
      saveBtn.disabled = false;
    }
  });
  bar.appendChild(saveBtn);

  programEl.appendChild(bar);
}

updateAuthUI();

// The session lives in an httpOnly cookie the server already validated on
// every request - this just asks it who (if anyone) that cookie belongs
// to, to restore the logged-in UI after a page reload.
(async function restoreSession() {
  const generation = authGeneration;
  try {
    const res = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (res.ok) {
      const data = await res.json();
      // a real logout (or a different login) may have landed while this
      // was in flight - don't resurrect a "logged in" UI over it
      if (generation !== authGeneration) return;
      auth = { username: data.username };
      updateAuthUI();
    }
  } catch (err) {
    // stay logged out - network error, nothing more to do here
  }
})();

// Language options come from /api/mode, not /api/languages: the local
// (no-API) mode only understands a couple of languages even though the
// dataset itself has instructions in ten - offering the rest would let
// the user pick a language that silently never matches anything.
(async function loadModeAndLanguages() {
  try {
    const res = await fetch("/api/mode");
    const data = await res.json();
    modeBadge.textContent = data.mode === "groq" ? "mode Groq" : "mode local (sans API)";

    langSelect.innerHTML = "";
    for (const lang of data.supported_langs) {
      const opt = document.createElement("option");
      opt.value = lang;
      opt.textContent = lang.toUpperCase();
      if (lang === "fr") opt.selected = true;
      langSelect.appendChild(opt);
    }
    if (!langSelect.value && langSelect.options.length) {
      langSelect.options[0].selected = true;
    }
  } catch (err) {
    modeBadge.textContent = "";
    langSelect.innerHTML = '<option value="fr" selected>FR</option>';
  }
})();

const programEl = document.getElementById("program");
const exerciseCache = new Map(); // id -> { lang, data }
let allLangsPromise = null;
let openId = null; // id of the exercise currently shown in the modal, if any

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  log.appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "end" });
  return div;
}

function cacheExercise(ex, lang) {
  exerciseCache.set(ex.id, { lang, data: ex });
}

let currentExercises = [];
let currentProgram = null;
// scope key ("results" or "day-N") -> mid-swap. Blocks a second swap in
// the same grid/day from starting until the first has fully resolved and
// re-rendered, so two concurrent requests can never both pick the same
// replacement (each fetch's `exclude` list is also recomputed live from
// current state at click time, not a snapshot from when the grid was
// last rendered).
const swappingScopes = new Set();

function siblingIdsFor(scopeKey) {
  if (scopeKey === "results") return currentExercises.map((e) => e.id);
  const dayIdx = Number(scopeKey.slice(4));
  return currentProgram.days[dayIdx].exercises.map((item) => item.exercise.id);
}

function makeCard(ex, lang, meta, scopeKey, onSwap) {
  const card = document.createElement("div");
  card.className = "card";

  const body = document.createElement("button");
  body.type = "button";
  body.className = "card-body";
  fillCardBody(body, ex, meta);
  body.addEventListener("click", () => {
    cacheExercise(ex, lang);
    openModal(ex.id);
  });
  card.appendChild(body);

  const swapBtn = document.createElement("button");
  swapBtn.type = "button";
  swapBtn.className = "swap-btn";
  swapBtn.title = lang === "fr" ? "Remplacer" : "Swap";
  swapBtn.textContent = "⟲";
  swapBtn.disabled = swappingScopes.has(scopeKey);
  swapBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (swappingScopes.has(scopeKey)) return;
    swappingScopes.add(scopeKey);
    swapBtn.disabled = true;
    try {
      const exclude = siblingIdsFor(scopeKey)
        .filter((id) => id !== ex.id)
        .join(",");
      const res = await fetch(`/api/exercise/${ex.id}/alternative?lang=${lang}&exclude=${exclude}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const alt = await res.json();
      // clear before onSwap's re-render so the freshly built buttons for
      // this scope come back enabled instead of permanently stuck
      swappingScopes.delete(scopeKey);
      onSwap(alt);
    } catch (err) {
      swappingScopes.delete(scopeKey);
      swapBtn.disabled = false;
    }
  });
  card.appendChild(swapBtn);

  return card;
}

function renderResults(exercises, lang) {
  currentExercises = exercises;
  results.innerHTML = "";
  exercises.forEach((ex, i) => {
    cacheExercise(ex, lang);
    results.appendChild(
      makeCard(ex, lang, null, "results", (alt) => {
        currentExercises[i] = alt;
        renderResults(currentExercises, lang);
      })
    );
  });
}

function renderProgram(program, lang) {
  currentProgram = program;
  programEl.innerHTML = "";
  const restLabel = lang === "fr" ? "repos" : "rest";
  program.days.forEach((day, dayIdx) => {
    const section = document.createElement("div");
    section.className = "day";
    const grid = document.createElement("div");
    grid.className = "grid";
    const scopeKey = `day-${dayIdx}`;
    day.exercises.forEach((item, itemIdx) => {
      const meta = `${item.sets} × ${item.reps} · ${restLabel} ${item.rest_seconds}s`;
      grid.appendChild(
        makeCard(item.exercise, lang, meta, scopeKey, (alt) => {
          currentProgram.days[dayIdx].exercises[itemIdx].exercise = alt;
          renderProgram(currentProgram, lang);
        })
      );
    });
    const h3 = document.createElement("h3");
    h3.textContent = day.label;
    section.appendChild(h3);
    section.appendChild(grid);
    programEl.appendChild(section);
  });
}

function renderSteps(exercise) {
  const stepsEl = document.getElementById("modal-steps");
  stepsEl.innerHTML = "";
  const steps = Array.isArray(exercise.instruction_steps) && exercise.instruction_steps.length
    ? exercise.instruction_steps
    : [exercise.instructions];
  for (const step of steps) {
    const li = document.createElement("li");
    li.textContent = step;
    stepsEl.appendChild(li);
  }
}

function fillModal(exercise) {
  document.getElementById("modal-img").src = exercise.gif_url;
  document.getElementById("modal-img").alt = exercise.name;
  document.getElementById("modal-name").textContent = exercise.name;
  document.getElementById("modal-tags").textContent =
    `${exercise.equipment.join(" + ")} · ${exercise.category} · ${exercise.target}`;
  renderSteps(exercise);
}

async function loadAllLangs() {
  if (!allLangsPromise) {
    allLangsPromise = fetch("/api/languages").then((r) => r.json());
  }
  return allLangsPromise;
}

let modalReturnFocus = null; // element to refocus once the modal closes

async function openModal(id) {
  const cached = exerciseCache.get(id);
  if (!cached) return;
  openId = id;
  modalReturnFocus = document.activeElement;
  fillModal(cached.data);

  const modalLang = document.getElementById("modal-lang");
  if (!modalLang.dataset.loaded) {
    const langs = await loadAllLangs();
    // openModal may have been called again (or the modal closed) while this awaited
    if (openId !== id) return;
    modalLang.innerHTML = "";
    for (const lang of langs) {
      const opt = document.createElement("option");
      opt.value = lang;
      opt.textContent = lang.toUpperCase();
      modalLang.appendChild(opt);
    }
    modalLang.dataset.loaded = "1";
  }
  modalLang.value = cached.lang;
  modalLang.onchange = async () => {
    const newLang = modalLang.value;
    const already = exerciseCache.get(id);
    if (already && already.lang === newLang) return;
    try {
      const res = await fetch(`/api/exercise/${id}?lang=${newLang}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const exercise = await res.json();
      // stale if the modal moved on to another exercise, or the user
      // picked yet another language before this fetch resolved
      if (openId !== id || modalLang.value !== newLang) return;
      cacheExercise(exercise, newLang);
      fillModal(exercise);
    } catch (err) {
      // keep showing the previous language rather than a broken modal
    }
  };

  document.getElementById("modal-overlay").classList.remove("hidden");
  document.getElementById("modal-close").focus();
}

function closeModal() {
  openId = null;
  document.getElementById("modal-overlay").classList.add("hidden");
  // return focus to whatever opened the modal (a card, typically) rather
  // than leaving it on a now-hidden element - but that card may have been
  // removed from the DOM in the meantime (e.g. a chat response re-rendered
  // the results grid while the modal was open), so check it's still there
  if (modalReturnFocus && document.body.contains(modalReturnFocus)) {
    modalReturnFocus.focus();
  }
  modalReturnFocus = null;
}

function trapModalTab(e) {
  const focusable = document
    .getElementById("modal")
    .querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

document.getElementById("modal-close").addEventListener("click", closeModal);
document.getElementById("modal-overlay").addEventListener("click", (e) => {
  if (e.target.id === "modal-overlay") closeModal();
});
document.addEventListener("keydown", (e) => {
  if (document.getElementById("modal-overlay").classList.contains("hidden")) return;
  if (e.key === "Escape") closeModal();
  else if (e.key === "Tab") trapModalTab(e);
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  addBubble("user", message);
  const pending = addBubble("assistant pending", "…");
  form.querySelector("button").disabled = true;
  langSelect.disabled = true;
  chatAbortController = new AbortController();
  cancelBtn.classList.remove("hidden");
  const requestLang = langSelect.value; // frozen: langSelect may change while this request is in flight

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...CSRF_HEADERS },
      body: JSON.stringify({ message, lang: requestLang, history }),
      signal: chatAbortController.signal,
    });
    if (res.status === 401) {
      clearAuth();
      throw new Error("Ta session a expiré, reconnecte-toi.");
    }
    if (res.status === 429) {
      throw new Error("Trop de requêtes, attends un peu avant de réessayer.");
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    pending.textContent = data.message;
    pending.className = "msg assistant";
    results.innerHTML = "";
    programEl.innerHTML = "";
    if (data.program && data.program.days && data.program.days.length) {
      renderProgram(data.program, requestLang);
      renderSaveToPlanBar(data.program, requestLang);
    } else {
      renderResults(data.exercises || [], requestLang);
    }
    history.push({ role: "user", text: message });
    history.push({ role: "assistant", text: data.message });
  } catch (err) {
    // our own throws above (401/429) already carry a user-facing message;
    // AbortController.abort() rejects fetch with an AbortError, not a
    // TypeError, so it needs its own message rather than falling into the
    // generic network-failure one below
    if (err instanceof DOMException && err.name === "AbortError") {
      pending.textContent = "Annulé.";
    } else {
      pending.textContent = err instanceof TypeError
        ? "Erreur : impossible de contacter l'assistant."
        : err.message;
    }
    pending.className = "msg assistant";
  } finally {
    form.querySelector("button").disabled = false;
    langSelect.disabled = false;
    cancelBtn.classList.add("hidden");
    chatAbortController = null;
    input.focus();
  }
});

cancelBtn.addEventListener("click", () => {
  chatAbortController?.abort();
});
