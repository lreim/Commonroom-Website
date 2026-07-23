(function () {
  let globalPreviewCard = null;
  let activeMobilePreviewLink = null;

  function isMobilePreviewMode() {
    return window.matchMedia("(max-width: 1380px)").matches;
  }

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
    if (activeMobilePreviewLink) {
      activeMobilePreviewLink.removeAttribute("data-preview-open");
      activeMobilePreviewLink = null;
    }
  }

  function showGlobalPreviewCard(user, evt) {
    const previewCard = ensureGlobalPreviewCard();
    const safeReason = user.match_reason || "Profile preview.";
    const safeName = user.name || user.username;
    const safeLocation = user.location ? `Location: ${user.location}` : "";
    const safeAbout = user.about_me || "";
    const safeLabels = user.profile_labels || [];
    const safeTags = (user.matching_tags && user.matching_tags.length > 0)
      ? user.matching_tags
      : (user.tags || []);

    previewCard.innerHTML = `
      <div class="profile-preview-header">
        <img class="profile-preview-avatar" src="${user.avatar_url || ""}" alt="${user.username}">
        <div class="profile-preview-heading">
          <div class="profile-preview-name">${safeName}</div>
        </div>
        ${safeLabels.length ? `<div class="profile-preview-header-labels">${safeLabels.join(", ")}</div>` : ""}
      </div>
      <div class="profile-preview-section">
        <div class="profile-preview-section-label">Matching tags</div>
        <div class="profile-preview-reason">${safeReason}</div>
      </div>
      ${safeLocation ? `
        <div class="profile-preview-section">
          <div class="profile-preview-section-label">Location</div>
          <div class="profile-preview-location">${safeLocation.replace(/^Location:\s*/, "")}</div>
        </div>
      ` : ""}
      ${safeAbout ? `
        <div class="profile-preview-section">
          <div class="profile-preview-section-label">About me</div>
          <div class="profile-preview-about">${safeAbout}</div>
        </div>
      ` : ""}
      ${safeTags.length ? `
        <div class="profile-preview-section">
          <div class="profile-preview-section-label">Tags</div>
          <div class="profile-preview-tags">${safeTags.join(", ")}</div>
        </div>
      ` : ""}
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
      link.addEventListener("click", function (evt) {
        if (!isMobilePreviewMode()) {
          return;
        }
        if (activeMobilePreviewLink === link) {
          return;
        }
        evt.preventDefault();
        evt.stopPropagation();
        hideGlobalPreviewCard();
        activeMobilePreviewLink = link;
        link.setAttribute("data-preview-open", "true");
        showGlobalPreviewCard(user, {
          clientX: evt.clientX || link.getBoundingClientRect().left,
          clientY: evt.clientY || link.getBoundingClientRect().bottom
        });
      });
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
    const storageKey = "commonroom_tagsearch_state";
    const input =
      root.querySelector("#tag-picker-input") || root.querySelector("#tag-search-input");
    const resultsEl = root.querySelector("#tag-search-results");
    const existingEl = root.querySelector("#tag-existing-list");
    const selectedEl = root.querySelector("#tag-selected-list");
    const profileLabelSelector = root.querySelector("#tagsearch-profile-label-selector");
    const profileLabelSummary = root.querySelector("#tagsearch-profile-label-summary");
    const profileLabelCheckboxes = profileLabelSelector
      ? Array.from(profileLabelSelector.querySelectorAll("[data-tagsearch-profile-label]"))
      : [];
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
    let currentMatches = [];

    function saveSearchState() {
      if (mode !== "search") return;
      const payload = {
        query: input ? input.value : "",
        selectedTags: Array.from(selected),
        selectedProfileLabels: getSelectedProfileLabels()
      };
      window.sessionStorage.setItem(storageKey, JSON.stringify(payload));
    }

    function restoreSearchState() {
      if (mode !== "search") return;
      const raw = window.sessionStorage.getItem(storageKey);
      if (!raw) return;
      try {
        const payload = JSON.parse(raw);
        selected = new Set((payload.selectedTags || []).map((tag) => String(tag).toLowerCase()));
        if (input && payload.query) {
          input.value = payload.query;
        }
        profileLabelCheckboxes.forEach((checkbox) => {
          checkbox.checked = (payload.selectedProfileLabels || []).includes(checkbox.value);
        });
      } catch (err) {
        window.sessionStorage.removeItem(storageKey);
      }
    }

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

    function getSearchQuery() {
      const typedQuery = input ? input.value.trim() : "";
      if (mode === "picker") {
        return typedQuery;
      }

      const parts = [];
      const seen = new Set();

      Array.from(selected)
        .sort()
        .forEach((tag) => {
          if (!seen.has(tag)) {
            seen.add(tag);
            parts.push(tag);
          }
        });

      if (typedQuery) {
        const normalizedTyped = typedQuery.toLowerCase();
        if (!seen.has(normalizedTyped)) {
          parts.push(typedQuery);
        }
      }

      return parts.join(", ");
    }

    function getSelectedProfileLabels() {
      return profileLabelCheckboxes
        .filter((checkbox) => checkbox.checked)
        .map((checkbox) => checkbox.value);
    }

    function updateProfileLabelSummary() {
      if (!profileLabelSummary) return;
      const labels = profileLabelCheckboxes
        .filter((checkbox) => checkbox.checked)
        .map((checkbox) => {
          const optionLabel = checkbox.closest(".profile-label-selector-option");
          const textNode = optionLabel ? optionLabel.querySelector("span") : null;
          return textNode ? textNode.textContent.trim() : "";
        })
        .filter(Boolean);
      profileLabelSummary.textContent = labels.length > 0
        ? labels.join(", ")
        : "No profile label selected";
    }

    function syncHidden() {
      const joined = Array.from(selected).sort().join(", ");
      if (hiddenInput) {
        hiddenInput.value = joined;
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
            saveSearchState();
            syncHidden();
            renderSelected();
            renderExisting();
            if (mode === "picker") {
              renderResults(currentMatches);
            } else {
              runSearch();
            }
          });
          selectedEl.appendChild(chip);
        });
    }

    function renderExisting() {
      if (!existingEl) return;
      existingEl.innerHTML = "";
      const matchedTagNames = new Set(
        currentMatches.map((match) => match.name.toLowerCase())
      );
      allTags.forEach((tag) => {
        const active = selected.has(tag.toLowerCase());
        const isMatched = matchedTagNames.has(tag.toLowerCase());
        let chipClass = "label label-default";
        if (active) {
          chipClass = "label label-primary";
        } else if (isMatched) {
          chipClass = "label label-default tag-existing-match";
        }
        const chip = createTagChip(tag, chipClass);
        chip.style.cursor = "pointer";
        chip.addEventListener("click", () => {
          const key = tag.toLowerCase();
          if (selected.has(key)) {
            selected.delete(key);
          } else {
            selected.add(key);
          }
          saveSearchState();
          if (mode === "picker") {
            syncHidden();
            renderSelected();
            renderExisting();
            renderResults(currentMatches);
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
      currentMatches = matches || [];
      renderExisting();
      resultsEl.innerHTML = "";
      const visibleMatches = mode === "picker"
        ? currentMatches.filter((m) => !selected.has(m.name.toLowerCase()))
        : currentMatches;

      if (!visibleMatches || visibleMatches.length === 0) {
        const p = document.createElement("p");
        p.className = "text-muted";
        p.textContent = "No matches yet.";
        resultsEl.appendChild(p);
        return;
      }

      visibleMatches.forEach((m) => {
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
            renderResults(currentMatches);
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
            const item = document.createElement("div");
            item.className = "tag-match-user-item";

            const link = document.createElement("a");
            const profileUrl = new URL(u.profile_url, window.location.origin);
            profileUrl.searchParams.set(
              "return_to",
              `${window.location.pathname}${window.location.search}${window.location.hash}`
            );
            link.href = profileUrl.toString();
            link.textContent = u.username;
            link.className = "tag-match-user-link";
            if (mode !== "picker") {
              link.addEventListener("mouseenter", (evt) => showPreviewCard(u, evt));
              link.addEventListener("mousemove", positionPreviewCard);
              link.addEventListener("mouseleave", hidePreviewCard);
              link.addEventListener("click", function (evt) {
                if (!isMobilePreviewMode()) {
                  return;
                }
                if (activeMobilePreviewLink === link) {
                  return;
                }
                evt.preventDefault();
                evt.stopPropagation();
                hidePreviewCard();
                activeMobilePreviewLink = link;
                link.setAttribute("data-preview-open", "true");
                showPreviewCard(u, {
                  clientX: evt.clientX || link.getBoundingClientRect().left,
                  clientY: evt.clientY || link.getBoundingClientRect().bottom
                });
              });
            }

            item.appendChild(link);
            usersList.appendChild(item);
          });

          usersWrap.appendChild(usersList);
          row.appendChild(usersWrap);
        }

        resultsEl.appendChild(row);
      });
    }

    async function runSearch() {
      if (!input) return;
      const q = getSearchQuery();
      if (!q) {
        if (statusEl) statusEl.textContent = "";
        renderResults([]);
        return;
      }
      try {
        const params = new URLSearchParams({ q });
        getSelectedProfileLabels().forEach((label) => params.append("labels", label));
        const url = `${endpoint}?${params.toString()}`;
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
        saveSearchState();
        debouncedSearch();
      });
    }
    profileLabelCheckboxes.forEach((checkbox) => {
      checkbox.addEventListener("change", function () {
        saveSearchState();
        updateProfileLabelSummary();
        runSearch();
      });
    });

    restoreSearchState();
    syncHidden();
    ensurePreviewCard();
    updateProfileLabelSummary();
    renderSelected();
    renderExisting();
    renderResults([]);
    if (mode === "search" && getSearchQuery()) {
      runSearch();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-tag-widget]").forEach(initTagWidget);
    bindProfilePreviewLinks();
  });

  document.addEventListener("click", function (evt) {
    if (!isMobilePreviewMode()) {
      return;
    }
    if (
      activeMobilePreviewLink &&
      !activeMobilePreviewLink.contains(evt.target) &&
      !(globalPreviewCard && globalPreviewCard.contains(evt.target))
    ) {
      hideGlobalPreviewCard();
    }
  });

  window.addEventListener("resize", function () {
    if (!isMobilePreviewMode()) {
      hideGlobalPreviewCard();
    }
  });
})();
