(function () {
  let globalPreviewCard = null;

  function ensureGlobalPreviewCard() {
    if (globalPreviewCard) return globalPreviewCard;
    globalPreviewCard = document.createElement("div");
    globalPreviewCard.className = "profile-preview-card";
    globalPreviewCard.style.display = "none";
    document.body.appendChild(globalPreviewCard);
    return globalPreviewCard;
  }

  function positionGlobalPreviewCard(evt) {
    if (!globalPreviewCard || globalPreviewCard.style.display === "none") return;
    const x = evt.clientX + 14;
    const y = evt.clientY + 14;
    globalPreviewCard.style.left = `${x}px`;
    globalPreviewCard.style.top = `${y}px`;
  }

  function hideGlobalPreviewCard() {
    if (!globalPreviewCard) return;
    globalPreviewCard.style.display = "none";
    globalPreviewCard.innerHTML = "";
  }

  function showGlobalPreviewCard(user, evt) {
    const previewCard = ensureGlobalPreviewCard();
    const safeReason = user.match_reason || "Profile preview.";
    const safeName = user.name || user.username;
    const safeLocation = user.location ? `Location: ${user.location}` : "";
    const safeAbout = user.about_me || "";
    const safeTags = (user.matching_tags && user.matching_tags.length > 0)
      ? user.matching_tags
      : (user.tags || []);

    previewCard.innerHTML = `
      <div class="profile-preview-header">
        <img class="profile-preview-avatar" src="${user.avatar_url || ""}" alt="${user.username}">
        <div>
          <div class="profile-preview-name">${safeName}</div>
          <div class="profile-preview-username">@${user.username}</div>
        </div>
      </div>
      <div class="profile-preview-reason">${safeReason}</div>
      ${safeLocation ? `<div class="profile-preview-location">${safeLocation}</div>` : ""}
      ${safeAbout ? `<div class="profile-preview-about">${safeAbout}</div>` : ""}
      ${safeTags.length ? `<div class="profile-preview-tags">Tags: ${safeTags.join(", ")}</div>` : ""}
    `;
    previewCard.style.display = "block";
    positionGlobalPreviewCard(evt);
  }

  function bindProfilePreviewLinks() {
    document.querySelectorAll("[data-profile-preview]").forEach((link) => {
      let user = null;
      try {
        user = JSON.parse(link.getAttribute("data-profile-preview") || "{}");
      } catch (err) {
        user = null;
      }
      if (!user || !user.username) return;
      link.addEventListener("mouseenter", (evt) => showGlobalPreviewCard(user, evt));
      link.addEventListener("mousemove", positionGlobalPreviewCard);
      link.addEventListener("mouseleave", hideGlobalPreviewCard);
    });
  }

  function debounce(fn, wait) {
    let t = null;
    return function debounced(...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function toTitle(text) {
    if (!text) return "";
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function createTagChip(name, className) {
    const span = document.createElement("span");
    span.className = className || "label label-default";
    span.style.display = "inline-block";
    span.style.margin = "0 6px 8px 0";
    span.textContent = name;
    return span;
  }

  function initTagWidget(root) {
    const mode = root.getAttribute("data-tag-widget");
    const endpoint = root.getAttribute("data-search-endpoint");
    const allTags = JSON.parse(root.getAttribute("data-all-tags") || "[]");
    const input =
      root.querySelector("#tag-picker-input") || root.querySelector("#tag-search-input");
    const resultsEl = root.querySelector("#tag-search-results");
    const existingEl = root.querySelector("#tag-existing-list");
    const selectedEl = root.querySelector("#tag-selected-list");
    let statusEl = root.querySelector("#tag-search-status");
    if (!statusEl) {
      statusEl = document.createElement("p");
      statusEl.id = "tag-search-status";
      statusEl.className = "text-muted";
      if (resultsEl && resultsEl.parentNode) {
        resultsEl.parentNode.insertBefore(statusEl, resultsEl);
      }
    }

    let hiddenInput = null;
    let selected = new Set();
    let previewCard = null;

    function ensurePreviewCard() {
      if (previewCard || mode === "picker") return;
      previewCard = ensureGlobalPreviewCard();
    }

    function positionPreviewCard(evt) {
      positionGlobalPreviewCard(evt);
    }

    function hidePreviewCard() {
      hideGlobalPreviewCard();
    }

    function showPreviewCard(user, evt) {
      ensurePreviewCard();
      if (!previewCard) return;
      showGlobalPreviewCard(
        Object.assign({ match_reason: "Profile matches your search." }, user),
        evt
      );
    }

    if (mode === "picker") {
      const hiddenId = root.getAttribute("data-hidden-input-id");
      hiddenInput = hiddenId ? document.getElementById(hiddenId) : null;
      const initial = hiddenInput && hiddenInput.value ? hiddenInput.value : "";
      initial
        .split(",")
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean)
        .forEach((t) => selected.add(t));
    }

    function syncHidden() {
      const joined = Array.from(selected).sort().join(", ");
      if (hiddenInput) {
        hiddenInput.value = joined;
      }
      if (mode !== "picker" && input && selected.size > 0) {
        input.value = joined;
      }
    }

    function renderSelected() {
      if (!selectedEl) return;
      selectedEl.innerHTML = "";
      if (selected.size === 0) {
        const p = document.createElement("p");
        p.className = "text-muted";
        p.textContent = "No tags selected.";
        selectedEl.appendChild(p);
        return;
      }
      Array.from(selected)
        .sort()
        .forEach((tag) => {
          const chip = createTagChip(tag, "label label-primary");
          chip.style.cursor = "pointer";
          chip.title = "Click to remove";
          chip.addEventListener("click", () => {
            selected.delete(tag);
            syncHidden();
            renderSelected();
            renderExisting();
            if (mode !== "picker") {
              runSearch();
            }
          });
          selectedEl.appendChild(chip);
        });
    }

    function renderExisting() {
      if (!existingEl) return;
      existingEl.innerHTML = "";
      allTags.forEach((tag) => {
        const active = selected.has(tag.toLowerCase());
        const chip = createTagChip(tag, active ? "label label-primary" : "label label-default");
        chip.style.cursor = "pointer";
        chip.addEventListener("click", () => {
          const key = tag.toLowerCase();
          if (selected.has(key)) {
            selected.delete(key);
          } else {
            selected.add(key);
          }
          if (mode === "picker") {
            syncHidden();
            renderSelected();
            renderExisting();
          } else {
            syncHidden();
            renderSelected();
            renderExisting();
            runSearch();
          }
        });
        existingEl.appendChild(chip);
      });
    }

    function renderResults(matches) {
      if (!resultsEl) return;
      resultsEl.innerHTML = "";
      if (!matches || matches.length === 0) {
        const p = document.createElement("p");
        p.className = "text-muted";
        p.textContent = "No matches yet.";
        resultsEl.appendChild(p);
        return;
      }

      matches.forEach((m) => {
        const row = document.createElement("div");
        row.style.marginBottom = "12px";

        const chip = createTagChip(m.name, "label label-info");
        chip.style.cursor = "pointer";
        chip.title = mode === "picker" ? "Click to toggle selection" : "Click to search this tag";
        chip.addEventListener("click", () => {
          const key = m.name.toLowerCase();
          if (selected.has(key)) {
            selected.delete(key);
          } else {
            selected.add(key);
          }
          if (mode === "picker") {
            syncHidden();
            renderSelected();
            renderExisting();
          } else {
            syncHidden();
            renderSelected();
            renderExisting();
            runSearch();
          }
        });

        const meta = document.createElement("small");
        meta.className = "text-muted";
        const reasonText = (m.reasons || []).map(toTitle).join(" + ");
        meta.textContent = ` score ${Number(m.score).toFixed(2)} (${reasonText})`;

        row.appendChild(chip);
        row.appendChild(meta);

        if (mode !== "picker" && m.users && m.users.length > 0) {
          const usersWrap = document.createElement("div");
          usersWrap.className = "tag-match-users";

          const usersLabel = document.createElement("small");
          usersLabel.className = "text-muted tag-match-users-label";
          usersLabel.textContent = "Matching profiles: ";
          usersWrap.appendChild(usersLabel);

          const usersList = document.createElement("div");
          usersList.className = "tag-match-users-list";

          m.users.forEach((u) => {
            const link = document.createElement("a");
            link.href = u.profile_url;
            link.textContent = u.username;
            link.className = "tag-match-user-link";
            if (mode !== "picker") {
              link.addEventListener("mouseenter", (evt) => showPreviewCard(u, evt));
              link.addEventListener("mousemove", positionPreviewCard);
              link.addEventListener("mouseleave", hidePreviewCard);
            }
            usersList.appendChild(link);
          });

          usersWrap.appendChild(usersList);
          row.appendChild(usersWrap);
        }

        resultsEl.appendChild(row);
      });
    }

    async function runSearch() {
      if (!input) return;
      const q = selected.size > 0 ? Array.from(selected).sort().join(", ") : input.value.trim();
      if (!q) {
        if (statusEl) statusEl.textContent = "";
        renderResults([]);
        return;
      }
      try {
        const url = `${endpoint}?q=${encodeURIComponent(q)}`;
        const resp = await fetch(url, { headers: { Accept: "application/json" } });
        const data = await resp.json();
        if (statusEl) {
          statusEl.textContent = data.semantic_model_ready
            ? "Semantic search active."
            : (data.error || "Semantic model unavailable.");
        }
        renderResults(data.matches || []);
      } catch (err) {
        if (statusEl) statusEl.textContent = "Search request failed.";
        renderResults([]);
      }
    }

    const debouncedSearch = debounce(runSearch, 220);
    if (input) {
      input.addEventListener("input", function () {
        if (mode !== "picker" && selected.size > 0) {
          selected.clear();
          renderSelected();
          renderExisting();
        }
        debouncedSearch();
      });
    }

    syncHidden();
    ensurePreviewCard();
    renderSelected();
    renderExisting();
    renderResults([]);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-tag-widget]").forEach(initTagWidget);
    bindProfilePreviewLinks();
  });
})();
