// Landing page — hero waveform + scroll reveal

(function initWaveform() {
  const canvas = document.getElementById("waveCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let phase = 0;
  let active = false;

  function ditherPixel(x, y) {
    return ((x + y * 7) & 3) === 0 ? 0.15 : 0;
  }

  function draw() {
    const { width, height } = canvas;
    ctx.clearRect(0, 0, width, height);

    const layers = [
      { color: "rgba(196, 165, 116, 0.45)", amp: 28, freq: 0.018, yOff: height * 0.38 },
      { color: "rgba(160, 130, 90, 0.3)", amp: 22, freq: 0.024, yOff: height * 0.52 },
      { color: "rgba(120, 95, 65, 0.22)", amp: 18, freq: 0.012, yOff: height * 0.62 },
    ];

    layers.forEach((layer, li) => {
      ctx.beginPath();
      ctx.fillStyle = layer.color;
      ctx.moveTo(0, height);
      for (let x = 0; x <= width; x += 2) {
        const drift = Math.sin(x * layer.freq + phase + li) * layer.amp;
        const ripple = Math.sin(x * 0.06 + phase * 1.4) * (active ? 10 : 4);
        const y = layer.yOff + drift + ripple;
        ctx.lineTo(x, y);
      }
      ctx.lineTo(width, height);
      ctx.closePath();
      ctx.fill();
    });

    const step = active ? 3 : 4;
    for (let y = 0; y < height; y += step) {
      for (let x = 0; x < width; x += step) {
        if (Math.random() > (active ? 0.72 : 0.88)) {
          ctx.fillStyle = `rgba(255,255,255,${0.08 + ditherPixel(x, y)})`;
          ctx.fillRect(x, y, 1, 1);
        }
      }
    }

    phase += active ? 0.035 : 0.012;
    requestAnimationFrame(draw);
  }

  window.setWaveActive = (on) => { active = on; };
  draw();
})();

(function initReveal() {
  const els = document.querySelectorAll(".reveal");
  if (!els.length) return;
  const io = new IntersectionObserver(
    (entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("visible")),
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
  );
  els.forEach((el) => io.observe(el));
  document.querySelectorAll(".hero .reveal").forEach((el) => {
    setTimeout(() => el.classList.add("visible"), 80);
  });
})();
