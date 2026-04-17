(function () {
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
      previewCard = document.createElement("div");
      previewCard.className = "profile-preview-card";
      previewCard.style.display = "none";
      document.body.appendChild(previewCard);
    }

    function positionPreviewCard(evt) {
      if (!previewCard || previewCard.style.display === "none") return;
      const x = evt.clientX + 14;
      const y = evt.clientY + 14;
      previewCard.style.left = `${x}px`;
      previewCard.style.top = `${y}px`;
    }

    function hidePreviewCard() {
      if (!previewCard) return;
      previewCard.style.display = "none";
      previewCard.innerHTML = "";
    }

    function showPreviewCard(user, evt) {
      ensurePreviewCard();
      if (!previewCard) return;
      const safeReason = user.match_reason || "Profile matches your search.";
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
      positionPreviewCard(evt);
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
      if (!hiddenInput) return;
      hiddenInput.value = Array.from(selected).sort().join(", ");
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
          if (mode === "picker") {
            chip.style.cursor = "pointer";
            chip.title = "Click to remove";
            chip.addEventListener("click", () => {
              selected.delete(tag);
              syncHidden();
              renderSelected();
              renderExisting();
            });
          }
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
          if (mode === "picker") {
            const key = tag.toLowerCase();
            if (selected.has(key)) {
              selected.delete(key);
            } else {
              selected.add(key);
            }
            syncHidden();
            renderSelected();
            renderExisting();
          } else if (input) {
            input.value = tag;
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
          if (mode === "picker") {
            const key = m.name.toLowerCase();
            if (selected.has(key)) {
              selected.delete(key);
            } else {
              selected.add(key);
            }
            syncHidden();
            renderSelected();
            renderExisting();
          } else if (input) {
            input.value = m.name;
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
          usersWrap.style.marginTop = "6px";

          const usersLabel = document.createElement("small");
          usersLabel.className = "text-muted";
          usersLabel.textContent = "Matching profiles: ";
          usersWrap.appendChild(usersLabel);

          m.users.forEach((u, idx) => {
            const link = document.createElement("a");
            link.href = u.profile_url;
            link.textContent = u.username;
            if (mode !== "picker") {
              link.addEventListener("mouseenter", (evt) => showPreviewCard(u, evt));
              link.addEventListener("mousemove", positionPreviewCard);
              link.addEventListener("mouseleave", hidePreviewCard);
            }
            usersWrap.appendChild(link);
            if (idx < m.users.length - 1) {
              usersWrap.appendChild(document.createTextNode(", "));
            }
          });
          row.appendChild(usersWrap);
        }

        resultsEl.appendChild(row);
      });
    }

    async function runSearch() {
      if (!input) return;
      const q = input.value.trim();
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
      input.addEventListener("input", debouncedSearch);
    }

    syncHidden();
    ensurePreviewCard();
    renderSelected();
    renderExisting();
    renderResults([]);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-tag-widget]").forEach(initTagWidget);
  });
})();
