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
    const margin = 12;
    const cardBounds = globalPreviewCard.getBoundingClientRect();
    const requestedX = evt.clientX + 14;
    const requestedY = evt.clientY + 14;
    const x = Math.max(
      margin,
      Math.min(requestedX, window.innerWidth - cardBounds.width - margin)
    );
    const y = Math.max(
      margin,
      Math.min(requestedY, window.innerHeight - cardBounds.height - margin)
    );
    globalPreviewCard.style.left = `${x}px`;
    globalPreviewCard.style.top = `${y}px`;
  }

  function hideGlobalPreviewCard() {
    if (!globalPreviewCard) return;
    globalPreviewCard.style.display = "none";
    globalPreviewCard.classList.remove("landing-scroll-profile-preview");
    globalPreviewCard.classList.remove("post-profile-preview");
    globalPreviewCard.style.right = "";
    globalPreviewCard.style.bottom = "";
    globalPreviewCard.style.width = "";
    globalPreviewCard.replaceChildren();
    if (activeMobilePreviewLink) {
      activeMobilePreviewLink.removeAttribute("data-preview-open");
      activeMobilePreviewLink = null;
    }
  }

  function appendPreviewSection(container, label, value, valueClassName) {
    if (!value) return;
    const section = document.createElement("div");
    section.className = "profile-preview-section";

    const sectionLabel = document.createElement("div");
    sectionLabel.className = "profile-preview-section-label";
    sectionLabel.textContent = label;

    const sectionValue = document.createElement("div");
    sectionValue.className = valueClassName;
    sectionValue.textContent = value;

    section.append(sectionLabel, sectionValue);
    container.appendChild(section);
  }

  function appendPreviewTags(container, tags) {
    if (!tags.length) return;
    const section = document.createElement("div");
    section.className = "profile-preview-section profile-preview-tags-section";

    const sectionLabel = document.createElement("div");
    sectionLabel.className = "profile-preview-section-label";
    sectionLabel.textContent = "Tags";

    const tagList = document.createElement("div");
    tagList.className = "profile-preview-tag-list";
    tags.forEach((tag) => {
      const chip = document.createElement("span");
      chip.className = "label label-info profile-preview-tag";
      chip.textContent = tag;
      tagList.appendChild(chip);
    });

    section.append(sectionLabel, tagList);
    container.appendChild(section);
  }

  function showGlobalPreviewCard(user, evt, trigger) {
    const previewCard = ensureGlobalPreviewCard();
    const safeAbout = user.about_me || "";
    const safeFunnyFact = user.funny_fact || "";
    const safeLabels = user.profile_labels || [];
    const safeTags = user.tags || [];

    previewCard.replaceChildren();
    previewCard.classList.toggle(
      "post-profile-preview",
      Boolean(trigger && trigger.closest(".post"))
    );

    const header = document.createElement("div");
    header.className = "profile-preview-header";

    const avatar = document.createElement("img");
    avatar.className = "profile-preview-avatar";
    avatar.src = user.avatar_url || "";
    avatar.alt = user.username || "";

    const heading = document.createElement("div");
    heading.className = "profile-preview-heading";

    const kicker = document.createElement("div");
    kicker.className = "profile-preview-kicker";
    kicker.textContent = "ANONYMOUS PROFILE";

    const name = document.createElement("div");
    name.className = "profile-preview-name";
    name.textContent = user.username;
    heading.append(kicker, name);

    if (safeLabels.length) {
      const labels = document.createElement("div");
      labels.className = "profile-preview-label-badges";
      safeLabels.forEach((label) => {
        const badge = document.createElement("span");
        badge.className = "profile-label-badge profile-preview-label-badge";
        badge.textContent = label;
        labels.appendChild(badge);
      });
      heading.appendChild(labels);
    }

    header.append(avatar, heading);

    previewCard.appendChild(header);
    appendPreviewSection(previewCard, "About me", safeAbout, "profile-preview-about");
    appendPreviewSection(previewCard, "Funny fact about me", safeFunnyFact, "profile-preview-funny-fact");
    appendPreviewTags(previewCard, safeTags);

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
      link.addEventListener("mouseenter", (evt) => showGlobalPreviewCard(user, evt, link));
      link.addEventListener("mousemove", positionGlobalPreviewCard);
      link.addEventListener("mouseleave", hideGlobalPreviewCard);
      link.addEventListener("commonroom:landing-preview-show", function () {
        if (!window.matchMedia("(max-width: 767px)").matches) return;
        showGlobalPreviewCard(user, { clientX: 0, clientY: 0 }, link);
        globalPreviewCard.classList.add("landing-scroll-profile-preview");
        globalPreviewCard.style.top = "auto";
        globalPreviewCard.style.right = "12px";
        globalPreviewCard.style.bottom = "148px";
        globalPreviewCard.style.left = "auto";
        globalPreviewCard.style.width = "min(82vw, 340px)";
      });
      link.addEventListener("commonroom:landing-preview-hide", hideGlobalPreviewCard);
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
        }, link);
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

        const isExactSelectedTag = selected.has(m.name.toLowerCase());
        const chip = createTagChip(
          m.name,
          isExactSelectedTag ? "label label-primary" : "label label-info"
        );
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
        const reasonText = (m.reasons || [])
          .filter((reason) => String(reason).toLowerCase() !== "lexical")
          .map(toTitle)
          .join(" + ");
        meta.textContent = ` score ${Number(m.score).toFixed(2)}${reasonText ? ` (${reasonText})` : ""}`;

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
