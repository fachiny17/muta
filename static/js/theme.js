/* Shared theme and low-cost ambient field. No network assets or dependencies. */
(() => {
  const toggle = document.getElementById("theme-toggle");
  const systemPrefersLight = () => window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  const readTheme = () => {
    try { return localStorage.getItem("muta_theme"); } catch (error) { return null; }
  };
  const writeTheme = (theme) => {
    try { localStorage.setItem("muta_theme", theme); } catch (error) { /* Storage may be disabled. */ }
  };
  const applyTheme = (theme) => {
    const isLight = theme === "light";
    document.body.classList.toggle("light-theme", isLight);
    document.body.classList.toggle("dark-theme", !isLight);
    if (!toggle) return;
    toggle.setAttribute("aria-pressed", String(isLight));
    toggle.setAttribute("aria-label", isLight ? "Switch to dark theme" : "Switch to light theme");
    toggle.setAttribute("title", isLight ? "Switch to dark theme" : "Switch to light theme");
  };

  const saved = readTheme();
  applyTheme(saved === "light" || saved === "dark" ? saved : "dark");
  if (toggle) toggle.addEventListener("click", () => {
    const next = document.body.classList.contains("light-theme") ? "dark" : "light";
    applyTheme(next);
    writeTheme(next);
  });

  const motionQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  if ((motionQuery && motionQuery.matches) || !document.body) return;
  const canvas = document.createElement("canvas");
  canvas.className = "ambient-canvas";
  canvas.setAttribute("aria-hidden", "true");
  canvas.setAttribute("role", "presentation");
  canvas.width = 1;
  canvas.height = 1;
  document.body.insertBefore(canvas, document.body.firstChild);
  const context = canvas.getContext("2d", { alpha: true });
  if (!context) { canvas.remove(); return; }

  let width = 1, height = 1, pixelRatio = 1, frame = 0, lastFrame = 0, scrollY = 0;
  let targetX = 0, targetY = 0, pointerX = 0, pointerY = 0;
  const particles = [];
  const count = () => Math.min(68, Math.max(28, Math.round(width * height / 19000)));
  const seed = () => {
    particles.length = 0;
    for (let i = 0; i < count(); i += 1) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        radius: .35 + Math.random() * 1.25,
        alpha: .16 + Math.random() * .52,
        speed: .025 + Math.random() * .10,
        drift: (Math.random() - .5) * .22,
        phase: Math.random() * Math.PI * 2,
        parallax: .15 + Math.random() * .75
      });
    }
  };
  const resize = () => {
    width = Math.max(1, window.innerWidth);
    height = Math.max(1, window.innerHeight);
    pixelRatio = Math.min(window.devicePixelRatio || 1, 1.35);
    canvas.width = Math.floor(width * pixelRatio);
    canvas.height = Math.floor(height * pixelRatio);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    seed();
    draw(performance.now ? performance.now() : Date.now(), true);
  };
  const draw = (time, staticFrame = false) => {
    context.clearRect(0, 0, width, height);
    const light = document.body.classList.contains("light-theme");
    const starColor = light ? "8, 94, 80" : "179, 218, 240";
    const mintColor = light ? "8, 125, 89" : "122, 244, 196";
    pointerX += (targetX - pointerX) * .035;
    pointerY += (targetY - pointerY) * .035;
    particles.forEach((particle) => {
      if (!staticFrame) {
        particle.y -= particle.speed;
        particle.x += particle.drift;
        if (particle.y < -3) { particle.y = height + 3; particle.x = Math.random() * width; }
        if (particle.x < -4) particle.x = width + 4;
        if (particle.x > width + 4) particle.x = -4;
      }
      const x = particle.x + pointerX * particle.parallax * 11;
      const y = particle.y + pointerY * particle.parallax * 9 - Math.min(36, scrollY * .025 * particle.parallax);
      const twinkle = staticFrame ? .9 : .68 + Math.sin(time * .0012 + particle.phase) * .25;
      context.beginPath();
      context.fillStyle = `rgba(${particle.radius > 1.25 ? mintColor : starColor},${Math.max(.06, particle.alpha * twinkle)})`;
      context.arc(x, y, particle.radius, 0, Math.PI * 2);
      context.fill();
      if (particle.radius > 1.2) {
        context.beginPath();
        context.strokeStyle = `rgba(${mintColor},${particle.alpha * .13})`;
        context.lineWidth = .5;
        context.moveTo(x - 4, y); context.lineTo(x + 4, y);
        context.moveTo(x, y - 4); context.lineTo(x, y + 4);
        context.stroke();
      }
    });
  };
  const animate = (time) => {
    if (document.hidden) { frame = 0; return; }
    if (time - lastFrame >= 33) { draw(time); lastFrame = time; }
    frame = window.requestAnimationFrame(animate);
  };
  const start = () => { if (!document.hidden && !frame) frame = window.requestAnimationFrame(animate); };
  const pause = () => { if (frame) window.cancelAnimationFrame(frame); frame = 0; };
  window.addEventListener("resize", resize, { passive: true });
  window.addEventListener("pointermove", (event) => {
    targetX = (event.clientX / Math.max(1, width) - .5) * 2;
    targetY = (event.clientY / Math.max(1, height) - .5) * 2;
  }, { passive: true });
  window.addEventListener("scroll", () => { scrollY = window.scrollY || 0; }, { passive: true });
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); else start(); });
  const motionChanged = (event) => {
    if (event.matches) { pause(); canvas.style.display = "none"; }
    else { canvas.style.display = ""; resize(); start(); }
  };
  if (motionQuery && motionQuery.addEventListener) motionQuery.addEventListener("change", motionChanged);
  else if (motionQuery && motionQuery.addListener) motionQuery.addListener(motionChanged);
  resize();
  start();
})();
