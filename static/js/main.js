// main.js — Dashboard logic for the AI Email Responder.
// ---------------------------------------------------------------------
// Talks to the JSON API exposed by app.py (/api/mails, /api/answers,
// /api/process). No framework — plain fetch + DOM updates, kept small
// on purpose since the whole site is meant to stay lightweight.
// ---------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  loadMails();
  loadAnswers();

  document.getElementById("btn-process").addEventListener("click", processInbox);
  document.getElementById("form-new-answer").addEventListener("submit", submitNewAnswer);
});

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str == null ? "" : String(str);
  return div.innerHTML;
}

async function apiFetch(url, options) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (response.status === 401 || response.status === 403) {
    window.location.href = "/login";
    return null;
  }
  return response;
}

// -----------------------------------------------------------------------
// Mails panel
// -----------------------------------------------------------------------

async function loadMails() {
  const container = document.getElementById("mail-list");
  try {
    const res = await apiFetch("/api/mails");
    if (!res) return;
    const mails = await res.json();

    document.getElementById("mail-count").textContent =
      mails.length ? `${mails.length} message(s) non lu(s)` : "";

    if (!mails.length) {
      container.innerHTML = '<p class="empty-note">Aucun message non lu pour le moment.</p>';
      return;
    }

    container.innerHTML = mails
      .map(
        (mail, i) => `
        <div class="ledger-row">
          <div class="ledger-row__num">${i + 1}</div>
          <div class="ledger-row__main">
            <strong>${escapeHtml(mail.subject || "(sans objet)")}</strong>
            <div class="ledger-row__meta">${escapeHtml(mail.from_addr || "")} — ${escapeHtml(mail.date || "")}</div>
            <div class="ledger-row__body">${escapeHtml((mail.body || "").slice(0, 180))}${(mail.body || "").length > 180 ? "…" : ""}</div>
          </div>
          <div class="row-actions"></div>
        </div>`
      )
      .join("");
  } catch (err) {
    container.innerHTML = '<p class="empty-note">Impossible de charger le courrier pour le moment.</p>';
  }
}

// -----------------------------------------------------------------------
// Answer base panel
// -----------------------------------------------------------------------

async function loadAnswers() {
  const container = document.getElementById("answer-list");
  try {
    const res = await apiFetch("/api/answers");
    if (!res) return;
    const answers = await res.json();

    document.getElementById("answer-count").textContent =
      answers.length ? `${answers.length} entrée(s)` : "";

    if (!answers.length) {
      container.innerHTML = '<p class="empty-note">Aucune entrée enregistrée. Ajoutez-en une ci-dessous.</p>';
      return;
    }

    container.innerHTML = answers.map((answer) => renderAnswerRow(answer)).join("");

    answers.forEach((answer) => {
      const editBtn = document.getElementById(`edit-btn-${answer.id}`);
      const delBtn = document.getElementById(`del-btn-${answer.id}`);
      const saveBtn = document.getElementById(`save-btn-${answer.id}`);
      if (editBtn) editBtn.addEventListener("click", () => toggleEdit(answer.id));
      if (delBtn) delBtn.addEventListener("click", () => deleteAnswer(answer.id));
      if (saveBtn) saveBtn.addEventListener("click", () => saveAnswer(answer.id));
    });
  } catch (err) {
    container.innerHTML = '<p class="empty-note">Impossible de charger la base de réponses.</p>';
  }
}

function renderAnswerRow(answer) {
  const keywords = (answer.keywords || []).map((k) => `<span class="tag">${escapeHtml(k)}</span>`).join("");
  return `
    <div class="ledger-row">
      <div class="ledger-row__num">${answer.id}</div>
      <div class="ledger-row__main">
        <strong>${escapeHtml((answer.template || "").slice(0, 90))}${(answer.template || "").length > 90 ? "…" : ""}</strong>
        <div class="tag-list">${keywords}</div>
        <div class="edit-fields" id="edit-fields-${answer.id}">
          <div class="field">
            <label for="edit-keywords-${answer.id}">Mots-clés</label>
            <input type="text" id="edit-keywords-${answer.id}" value="${escapeHtml((answer.keywords || []).join(", "))}">
          </div>
          <div class="field">
            <label for="edit-template-${answer.id}">Modèle</label>
            <textarea id="edit-template-${answer.id}">${escapeHtml(answer.template || "")}</textarea>
          </div>
          <button class="btn btn--small" id="save-btn-${answer.id}">Enregistrer</button>
        </div>
      </div>
      <div class="row-actions">
        <button class="btn btn--ghost btn--small" id="edit-btn-${answer.id}">Modifier</button>
        <button class="btn btn--danger btn--small" id="del-btn-${answer.id}">Supprimer</button>
      </div>
    </div>`;
}

function toggleEdit(id) {
  const fields = document.getElementById(`edit-fields-${id}`);
  fields.classList.toggle("is-open");
}

async function saveAnswer(id) {
  const keywords = document.getElementById(`edit-keywords-${id}`).value;
  const template = document.getElementById(`edit-template-${id}`).value;

  const res = await apiFetch(`/api/answers/${id}`, {
    method: "PUT",
    body: JSON.stringify({ keywords, template }),
  });
  if (!res) return;
  if (res.ok) loadAnswers();
}

async function deleteAnswer(id) {
  if (!window.confirm("Supprimer cette entrée du registre ?")) return;
  const res = await apiFetch(`/api/answers/${id}`, { method: "DELETE" });
  if (!res) return;
  if (res.ok) loadAnswers();
}

async function submitNewAnswer(event) {
  event.preventDefault();
  const keywords = document.getElementById("new-keywords").value;
  const template = document.getElementById("new-template").value;

  const res = await apiFetch("/api/answers", {
    method: "POST",
    body: JSON.stringify({ keywords, template }),
  });
  if (!res) return;
  if (res.ok) {
    document.getElementById("form-new-answer").reset();
    loadAnswers();
  }
}

// -----------------------------------------------------------------------
// Manual trigger
// -----------------------------------------------------------------------

async function processInbox() {
  const btn = document.getElementById("btn-process");
  const result = document.getElementById("process-result");
  btn.disabled = true;
  btn.textContent = "Traitement en cours…";

  try {
    const res = await apiFetch("/api/process", { method: "POST" });
    if (!res) return;
    const data = await res.json();
    result.style.display = "block";
    result.textContent = `${data.processed} message(s) examiné(s), ${data.replies_sent} réponse(s) envoyée(s).`;
    loadMails();
  } catch (err) {
    result.style.display = "block";
    result.textContent = "Le traitement a échoué. Vérifiez la configuration IMAP/SMTP.";
  } finally {
    btn.disabled = false;
    btn.textContent = "Traiter la boîte maintenant";
  }
}
