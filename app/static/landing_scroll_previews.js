(function () {
  const landingPage = document.querySelector(".welcome-hero");
  const mobileQuery = window.matchMedia("(max-width: 767px)");

  if (!landingPage || !mobileQuery.matches || !("IntersectionObserver" in window)) {
    return;
  }

  const bubbleLinks = Array.from(document.querySelectorAll(".welcome-bubble-link"));
  const profileLinks = Array.from(document.querySelectorAll(".homepage-profile-preview-trigger[data-profile-preview]"));

  function observeCentered(elements, show, hide) {
    if (elements.length === 0) return;

    const intersecting = new Set();
    let activeElement = null;

    function updateActiveElement() {
      const viewportCenter = window.innerHeight / 2;
      const nextElement = Array.from(intersecting).sort(function (a, b) {
        const aRect = a.getBoundingClientRect();
        const bRect = b.getBoundingClientRect();
        const aDistance = Math.abs((aRect.top + aRect.bottom) / 2 - viewportCenter);
        const bDistance = Math.abs((bRect.top + bRect.bottom) / 2 - viewportCenter);
        return aDistance - bDistance;
      })[0] || null;

      if (nextElement === activeElement) return;
      if (activeElement) hide(activeElement);
      activeElement = nextElement;
      if (activeElement) show(activeElement);
    }

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          intersecting.add(entry.target);
        } else {
          intersecting.delete(entry.target);
        }
      });
      updateActiveElement();
    }, {
      root: null,
      rootMargin: "-34% 0px -34% 0px",
      threshold: 0.05,
    });

    elements.forEach(function (element) {
      observer.observe(element);
    });
  }

  observeCentered(
    bubbleLinks,
    function (link) { link.classList.add("is-scroll-preview"); },
    function (link) { link.classList.remove("is-scroll-preview"); }
  );

  observeCentered(
    profileLinks,
    function (link) {
      link.dispatchEvent(new CustomEvent("commonroom:landing-preview-show"));
    },
    function (link) {
      link.dispatchEvent(new CustomEvent("commonroom:landing-preview-hide"));
    }
  );
})();
