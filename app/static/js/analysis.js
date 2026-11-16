"use strict";

// Shared menu behavior. Navigation URLs are rendered by Flask/Jinja.
const menuButton = document.getElementById("menuButton");
const menu = document.getElementById("menu");
const menuClose = document.getElementById("menuClose");
if (menu && menuButton && menuClose) {
  menuButton.addEventListener("click", () => {
    menu.classList.add("active");
    menuButton.style.display = "none";
  });
  menuClose.addEventListener("click", () => {
    menu.classList.remove("active");
    menuButton.style.display = "flex";
  });
}

// Follow-up answers are submitted as an HTML POST form, not simulated in JS.
const chatForm = document.getElementById("chatForm");
if (chatForm) {
  chatForm.addEventListener("submit", () => {
    if (!chatForm.reportValidity()) return;
    const button = document.getElementById("answerSubmit");
    if (button) {
      button.disabled = true;
      button.textContent = "分析を再開しています...";
    }
  });
}

// Analyze with a real POST; only server result determines next page.
if (document.body?.dataset.analysisPage === "analyzing") {
  const status = document.getElementById("analysis-status");
  const error = document.getElementById("analysis-error");
  const retry = document.getElementById("analysis-retry");
  const runUrl = document.body.dataset.runUrl;
  const csrfToken = document.body.dataset.csrfToken;
  let submitting = false;

  async function beginAnalysis() {
    if (submitting) return;
    submitting = true;
    if (retry) retry.hidden = true;
    if (error) { error.textContent = ""; error.hidden = true; }
    if (status) status.textContent = "サーバーがAI分析を処理しています。しばらくお待ちください。";
    try {
      const response = await fetch(runUrl, {
        method: "POST",
        headers: {
          "X-CSRF-Token": csrfToken,
          "Accept": "application/json"
        },
        credentials: "same-origin"
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.error === "string" ? data.error : "分析要求を処理できませんでした。");
      }
      if (!data || typeof data.redirect_url !== "string") {
        throw new Error("サーバーから予期しない応答がありました。");
      }
      const destination = new URL(data.redirect_url, window.location.href);
      if (destination.origin !== window.location.origin ||
          !destination.pathname.startsWith(new URL(runUrl, window.location.href).pathname.replace(/\/run$/, "") + "/")) {
        throw new Error("無効な移動先が指定されました。");
      }
      window.location.assign(destination.href);
    } catch (err) {
      if (status) status.textContent = "分析を開始・継続できませんでした。";
      if (error) {
        error.textContent = err instanceof Error ? err.message : "通信エラーが発生しました。";
        error.hidden = false;
      }
      if (retry) retry.hidden = false;
    } finally {
      submitting = false;
    }
  }

  if (retry) retry.addEventListener("click", beginAnalysis);
  beginAnalysis();
}
