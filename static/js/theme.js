/* Shared theme and low-cost ambient field. No network assets or dependencies. */
(() => {
  const toggle = document.getElementById("theme-toggle");

  const systemPrefersLight = () =>
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches;

  const readTheme = () => {
    try {
      return localStorage.getItem("muta_theme");
    } catch (error) {
      return null;
    }
  };

  const writeTheme = (theme) => {
    try {
      localStorage.setItem("muta_theme", theme);
    } catch (error) {
      /* Storage may be disabled. */
    }
  };

  const applyTheme = (theme) => {
    const isLight = theme === "light";

    document.body.classList.toggle("light-theme", isLight);
    document.body.classList.toggle("dark-theme", !isLight);

    if (!toggle) return;

    toggle.setAttribute("aria-pressed", String(isLight));
    toggle.setAttribute(
      "aria-label",
      isLight ? "Switch to dark theme" : "Switch to light theme"
    );
    toggle.setAttribute(
      "title",
      isLight ? "Switch to dark theme" : "Switch to light theme"
    );
  };

  const saved = readTheme();

  applyTheme(
    saved === "light" || saved === "dark"
      ? saved
      : systemPrefersLight()
        ? "light"
        : "dark"
  );

  if (toggle) {
    toggle.addEventListener("click", () => {
      const next = document.body.classList.contains("light-theme")
        ? "dark"
        : "light";

      applyTheme(next);
      writeTheme(next);
    });
  }

  /* Mobile navigation menu */
  const header = document.querySelector(".header");
  const menuToggle = document.getElementById("menu-toggle");
  const mainNavigation = document.getElementById("main-navigation");

  if (header && menuToggle && mainNavigation) {
    const setMenuOpen = (open) => {
      header.classList.toggle("menu-open", open);

      menuToggle.setAttribute("aria-expanded", String(open));
      menuToggle.setAttribute(
        "aria-label",
        open ? "Close navigation menu" : "Open navigation menu"
      );
      menuToggle.setAttribute(
        "title",
        open ? "Close navigation menu" : "Open navigation menu"
      );
    };

    menuToggle.addEventListener("click", () => {
      setMenuOpen(!header.classList.contains("menu-open"));
    });

    mainNavigation.addEventListener("click", (event) => {
      if (event.target.closest("a, button")) {
        setMenuOpen(false);
      }
    });

    document.addEventListener("pointerdown", (event) => {
      if (!header.contains(event.target)) {
        setMenuOpen(false);
      }
    });

    document.addEventListener("keydown", (event) => {
      if (
        event.key === "Escape" &&
        header.classList.contains("menu-open")
      ) {
        setMenuOpen(false);
        menuToggle.focus();
      }
    });

    window.addEventListener(
      "resize",
      () => {
        if (window.innerWidth > 520) {
          setMenuOpen(false);
        }
      },
      { passive: true }
    );
  }

  /* Respect the user's reduced-motion preference. */
  const motionQuery = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;

  if (
    (motionQuery && motionQuery.matches) ||
    !document.body
  ) {
    return;
  }

  /* Create the ambient Canvas without external dependencies. */
  const canvas = document.createElement("canvas");

  canvas.className = "ambient-canvas";
  canvas.setAttribute("aria-hidden", "true");
  canvas.setAttribute("role", "presentation");
  canvas.width = 1;
  canvas.height = 1;

  document.body.insertBefore(canvas, document.body.firstChild);

  const context = canvas.getContext("2d", { alpha: true });

  if (!context) {
    canvas.remove();
    return;
  }

  let width = 1;
  let height = 1;
  let pixelRatio = 1;
  let frame = 0;
  let lastFrame = 0;
  let scrollY = 0;

  let targetX = 0;
  let targetY = 0;
  let pointerX = 0;
  let pointerY = 0;

  const particles = [];

  /* Denser star field, capped to protect lower-powered devices. */
  const count = () =>
    Math.min(
      128,
      Math.max(72, Math.round((width * height) / 11000))
    );

  const seed = () => {
    particles.length = 0;

    for (let i = 0; i < count(); i += 1) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        radius: 0.55 + Math.random() * 1.45,
        alpha: 0.30 + Math.random() * 0.58,
        speed: 0.025 + Math.random() * 0.10,
        drift: (Math.random() - 0.5) * 0.22,
        phase: Math.random() * Math.PI * 2,
        parallax: 0.15 + Math.random() * 0.75,
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

    draw(
      performance.now ? performance.now() : Date.now(),
      true
    );
  };

  /* Paint soft nebula clouds while preserving the blue page background. */
  const paintNebula = (
    x,
    y,
    radius,
    stretch,
    rotation,
    light
  ) => {
    context.save();

    context.translate(x, y);
    context.rotate(rotation);
    context.scale(1, stretch);

    const gradient = context.createRadialGradient(
      0,
      0,
      0,
      0,
      0,
      radius
    );

    gradient.addColorStop(
      0,
      light
        ? "rgba(45,112,190,.10)"
        : "rgba(35,113,255,.30)"
    );

    gradient.addColorStop(
      0.28,
      light
        ? "rgba(62,124,196,.07)"
        : "rgba(31,101,255,.20)"
    );

    gradient.addColorStop(
      0.58,
      light
        ? "rgba(105,91,178,.035)"
        : "rgba(127,61,255,.13)"
    );

    gradient.addColorStop(1, "rgba(0,0,0,0)");

    context.fillStyle = gradient;

    context.beginPath();
    context.arc(0, 0, radius, 0, Math.PI * 2);
    context.fill();

    context.restore();
  };

  /* Draw a galaxy using four curved spiral arms. */
  const drawGalaxy = (time, light) => {
    const cx = width * 0.70;
    const cy = height * 0.31;
    const scale = Math.min(width * 0.58, height * 0.44, 350);

    paintNebula(
      cx,
      cy,
      scale * 1.72,
      0.58,
      -0.32,
      light
    );

    paintNebula(
      width * 0.18,
      height * 0.76,
      Math.min(width * 0.42, height * 0.32, 245),
      0.60,
      0.35,
      light
    );

    context.save();

    context.translate(cx, cy);
    context.rotate(-0.20 + Math.sin(time * 0.00008) * 0.018);

    for (let arm = 0; arm < 4; arm += 1) {
      context.save();
      context.rotate((arm * Math.PI) / 2);

      context.beginPath();

      for (let i = 0; i <= 108; i += 1) {
        const progress = i / 108;
        const angle = progress * Math.PI * 2.6;
        const radius = 4 + progress * scale;

        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius * 0.50;

        if (i === 0) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      }

      /* Soft, wider glow beneath each spiral arm. */
      context.strokeStyle = light
        ? "rgba(49,113,194,.10)"
        : "rgba(58,133,255,.23)";

      context.lineWidth = light ? 5 : 8;

      context.shadowColor = light
        ? "rgba(55,121,205,.10)"
        : "rgba(48,119,255,.25)";

      context.shadowBlur = light ? 8 : 18;

      context.stroke();

      /* Fine cyan edge for additional definition. */
      context.shadowBlur = 0;

      context.strokeStyle = light
        ? "rgba(44,117,190,.11)"
        : "rgba(107,207,255,.32)";

      context.lineWidth = 1;
      context.stroke();

      context.restore();
    }

    /* Bright galaxy centre. */
    const core = context.createRadialGradient(
      0,
      0,
      0,
      0,
      0,
      Math.max(9, scale * 0.18)
    );

    core.addColorStop(
      0,
      light
        ? "rgba(220,239,255,.26)"
        : "rgba(229,247,255,.78)"
    );

    core.addColorStop(
      0.20,
      light
        ? "rgba(77,157,233,.15)"
        : "rgba(91,197,255,.46)"
    );

    core.addColorStop(1, "rgba(0,0,0,0)");

    context.fillStyle = core;
    context.beginPath();
    context.arc(0, 0, Math.max(9, scale * 0.18), 0, Math.PI * 2);
    context.fill();

    context.restore();
  };

  /* Render the galaxy and floating stars. */
  const draw = (time, staticFrame = false) => {
    context.clearRect(0, 0, width, height);

    const light = document.body.classList.contains("light-theme");

    const starColor = light
      ? "56,104,166"
      : "184,221,255";

    const accentColor = light
      ? "54,131,195"
      : "91,218,255";

    pointerX += (targetX - pointerX) * 0.035;
    pointerY += (targetY - pointerY) * 0.035;

    /* Galaxy first, stars afterwards. */
    drawGalaxy(time, light);

    particles.forEach((particle) => {
      if (!staticFrame) {
        particle.y -= particle.speed;
        particle.x += particle.drift;

        if (particle.y < -3) {
          particle.y = height + 3;
          particle.x = Math.random() * width;
        }

        if (particle.x < -4) {
          particle.x = width + 4;
        }

        if (particle.x > width + 4) {
          particle.x = -4;
        }
      }

      const x =
        particle.x + pointerX * particle.parallax * 11;

      const y =
        particle.y +
        pointerY * particle.parallax * 9 -
        Math.min(
          36,
          scrollY * 0.025 * particle.parallax
        );

      const twinkle = staticFrame
        ? 0.9
        : 0.68 +
          Math.sin(time * 0.0012 + particle.phase) * 0.25;

      const alpha = Math.max(
        0.10,
        particle.alpha * twinkle
      );

      const bright = particle.radius > 1.45;

      context.beginPath();

      context.fillStyle =
        `rgba(${bright ? accentColor : starColor},${alpha})`;

      context.shadowBlur = bright && !light ? 5 : 0;
      context.shadowColor = `rgba(${accentColor},.8)`;

      context.arc(
        x,
        y,
        particle.radius,
        0,
        Math.PI * 2
      );

      context.fill();
      context.shadowBlur = 0;

      /* Small glints on the brighter stars. */
      if (particle.radius > 1.65) {
        context.beginPath();

        context.strokeStyle =
          `rgba(${accentColor},${alpha * 0.38})`;

        context.lineWidth = 0.65;

        context.moveTo(x - 4, y);
        context.lineTo(x + 4, y);

        context.moveTo(x, y - 4);
        context.lineTo(x, y + 4);

        context.stroke();
      }
    });
  };

  /* Animation loop: avoid excessive redraws on mobile devices. */
  const animate = (time) => {
    if (document.hidden) {
      frame = 0;
      return;
    }

    if (time - lastFrame >= 33) {
      draw(time);
      lastFrame = time;
    }

    frame = window.requestAnimationFrame(animate);
  };

  const start = () => {
    if (!document.hidden && !frame) {
      frame = window.requestAnimationFrame(animate);
    }
  };

  const pause = () => {
    if (frame) {
      window.cancelAnimationFrame(frame);
    }

    frame = 0;
  };

  window.addEventListener("resize", resize, {
    passive: true,
  });

  window.addEventListener(
    "pointermove",
    (event) => {
      targetX =
        (event.clientX / Math.max(1, width) - 0.5) * 2;

      targetY =
        (event.clientY / Math.max(1, height) - 0.5) * 2;
    },
    { passive: true }
  );

  window.addEventListener(
    "scroll",
    () => {
      scrollY = window.scrollY || 0;
    },
    { passive: true }
  );

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      pause();
    } else {
      start();
    }
  });

  /* Stop motion if the user enables reduced motion. */
  const motionChanged = (event) => {
    if (event.matches) {
      pause();
      canvas.style.display = "none";
    } else {
      canvas.style.display = "";
      resize();
      start();
    }
  };

  if (motionQuery && motionQuery.addEventListener) {
    motionQuery.addEventListener("change", motionChanged);
  } else if (motionQuery && motionQuery.addListener) {
    motionQuery.addListener(motionChanged);
  }

  resize();
  start();
})();