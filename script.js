(function () {

  /* ── Theme Picker ── */
  const html = document.documentElement;
  const toggle = document.getElementById("themeToggle");
  const menu = document.getElementById("themeMenu");
  const opts = document.querySelectorAll(".theme-opt");
  let menuOpen = false;

  function setTheme(name) {
    html.setAttribute("data-theme", name);
    opts.forEach(function (b) {
      b.classList.toggle("active", b.getAttribute("data-theme-name") === name);
    });
    try { localStorage.setItem("vigil-theme", name); } catch (_) {}
  }

  var saved = (function () {
    try { return localStorage.getItem("vigil-theme"); } catch (_) { return null; }
  })();
  if (saved) { setTheme(saved); }

  toggle.addEventListener("click", function (e) {
    e.stopPropagation();
    menuOpen = !menuOpen;
    menu.classList.toggle("open", menuOpen);
  });

  opts.forEach(function (b) {
    b.addEventListener("click", function () {
      setTheme(b.getAttribute("data-theme-name"));
      menuOpen = false;
      menu.classList.remove("open");
    });
  });

  document.addEventListener("click", function () {
    if (menuOpen) { menuOpen = false; menu.classList.remove("open"); }
  });

  /* ── Voice Demo ── */
  var voiceBtn = document.getElementById("voiceDemoBtn");
  if (voiceBtn && "speechSynthesis" in window) {
    voiceBtn.addEventListener("click", function () {
      if (voiceBtn.classList.contains("playing")) {
        window.speechSynthesis.cancel();
        voiceBtn.classList.remove("playing");
        return;
      }
      var text = "Deal alert from Deals Group. Price target at forty five hundred. Priority message from Joy. Meeting confirmed for tomorrow. You have three new important alerts.";
      var utter = new SpeechSynthesisUtterance(text);
      utter.rate = 0.9;
      utter.pitch = 1.0;
      utter.onend = function () { voiceBtn.classList.remove("playing"); };
      utter.onerror = function () { voiceBtn.classList.remove("playing"); };
      voiceBtn.classList.add("playing");
      window.speechSynthesis.speak(utter);
    });
  }

  /* ── Scroll → fade-in sections ── */
  var sectionLabels = document.querySelectorAll(".section-label");
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) {
        e.target.style.opacity = "1";
        e.target.style.transform = "translateY(0)";
      }
    });
  }, { threshold: 0.15 });

  sectionLabels.forEach(function (el) {
    el.style.opacity = "0";
    el.style.transform = "translateY(12px)";
    el.style.transition = "opacity 0.5s ease, transform 0.5s ease";
    observer.observe(el);
  });

})();
