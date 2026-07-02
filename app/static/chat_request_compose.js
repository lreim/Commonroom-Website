(function () {
  function requestTemplate(username) {
    return [
      `Hi ${username},`,
      "",
      "I found your profile on CommonRoom and would like to start a conversation with you.",
      "",
      "What I would like to talk about:",
      "- ",
      "",
      "Why I am reaching out:",
      "- ",
      "",
      "No pressure to accept if this does not fit for you."
    ].join("\n");
  }

  function initInlineChatRequest(root) {
    const composePanel = root.querySelector("[data-chat-request-compose]");
    const composeTitle = root.querySelector("[data-chat-request-title]");
    const composeMessage = root.querySelector("[data-chat-request-message]");
    const requestedUserId = root.querySelector("[data-chat-request-user-id]");
    const cancelButton = root.querySelector("[data-chat-request-cancel]");
    const nextInput = root.querySelector("[data-chat-request-next]");

    if (!composePanel || !composeTitle || !composeMessage || !requestedUserId || !cancelButton || !nextInput) {
      return;
    }

    function openCompose(userId, username) {
      requestedUserId.value = userId;
      composeTitle.textContent = `Send chat request to ${username}`;
      composeMessage.value = requestTemplate(username);
      nextInput.value = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      composePanel.style.display = "block";
      composeMessage.focus();
    }

    function closeCompose() {
      composePanel.style.display = "none";
      requestedUserId.value = "";
      composeMessage.value = "";
    }

    root.addEventListener("click", function (event) {
      const button = event.target.closest("[data-inline-chat-request]");
      if (!button) {
        return;
      }
      event.preventDefault();
      openCompose(button.dataset.requestUserId, button.dataset.requestUsername);
    });

    cancelButton.addEventListener("click", function () {
      closeCompose();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-inline-chat-request-root]").forEach(initInlineChatRequest);
  });
})();
