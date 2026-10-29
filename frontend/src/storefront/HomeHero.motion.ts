// One compositor timeline per cigar and shadow. JavaScript runs only on events
// and resize, never on animation frames.
const TAU = Math.PI * 2;
const STEPS = 96;
export const heroPositions = [
  { x: 1, y: 22, w: 91, r: -8, depth: .45 },
  { x: 17, y: 38, w: 78, r: 4, depth: .8 },
  { x: 4, y: 53, w: 75, r: -4, depth: .55 },
  { x: 22, y: 67, w: 63, r: 7, depth: 1 },
  { x: 10, y: 80, w: 61, r: -5, depth: .2 },
] as const;

type Pose = { y: number; r: number };
export type Orbit = {
  phase: number;
  cycle: number;
  baseR: number;
  held: boolean;
  bobPhase: number;
  anchor: Pose;
  releasing: boolean;
  poses: Pose[];
};
export function createOrbit(index: number): Orbit {
  const cycle = 6500 + index * 850;
  return { phase: index * 1100 / cycle * TAU, cycle, baseR: heroPositions[index].r,
    held: false, bobPhase: 0, anchor: { y: 0, r: 0 }, releasing: false, poses: [] };
}

// Sample the same piecewise-linear keyframes as WAAPI, including a completed
// one-shot release. This avoids a layout/style read when hover changes.
export function orbitPose(orbit: Orbit, elapsed: number): Pose {
  if (!orbit.poses.length) {
    const y = Math.sin(orbit.phase);
    return { y, r: orbit.baseR + y * 1.4 };
  }
  const progress = orbit.releasing ? Math.min(elapsed / orbit.cycle, 1) : (elapsed / orbit.cycle) % 1;
  const position = Math.max(0, progress) * STEPS;
  const index = Math.min(Math.floor(position), STEPS - 1);
  const mix = position - index;
  const a = orbit.poses[index], b = orbit.poses[index + 1];
  return { y: a.y + (b.y - a.y) * mix, r: a.r + (b.r - a.r) * mix };
}

export function rebaseOrbit(orbit: Orbit, held: boolean, elapsed: number): Pose[] {
  const current = orbitPose(orbit, elapsed);
  // Held time never advances the free orbit, so leaving hover cannot catch up.
  if (!orbit.held) orbit.phase = (orbit.phase + elapsed / orbit.cycle * TAU) % TAU;
  if (held) {
    if (!orbit.held) { orbit.anchor = current; orbit.bobPhase = 0; }
    else orbit.bobPhase = (orbit.bobPhase + elapsed / orbit.cycle * TAU) % TAU;
  }
  const releaseY = current.y - Math.sin(orbit.phase);
  const releaseR = current.r - (orbit.baseR + Math.sin(orbit.phase) * 1.4);
  orbit.releasing = !held && (Math.abs(releaseY) > .0001 || Math.abs(releaseR) > .0001);
  orbit.held = held;
  orbit.poses = Array.from({ length: STEPS + 1 }, (_, step) => {
    const t = step / STEPS;
    const wave = Math.sin(orbit.phase + t * TAU);
    const residual = orbit.releasing ? 1 - t * t * (3 - 2 * t) : 0;
    const bob = Math.sin(orbit.bobPhase + t * TAU);
    return held
      ? { y: orbit.anchor.y + .22 * bob, r: orbit.anchor.r + .35 * bob }
      : { y: wave + releaseY * residual, r: orbit.baseR + wave * 1.4 + releaseR * residual };
  });
  return orbit.poses;
}

export function mountHeroMotion(stage: HTMLElement) {
  if (!stage.animate || !window.matchMedia || !window.ResizeObserver || !window.IntersectionObserver) return;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let paused = false, inView = true, disposed = false, width = 0, height = 0;
  const removers: (() => void)[] = [];
  const figures = Array.from(stage.querySelectorAll<HTMLElement>('.store-home-hero__cigar'));
  const shadows = Array.from(stage.querySelectorAll<HTMLElement>('.store-home-hero__shadow'));
  const nodes = figures.map((figure, index) => ({
    figure, shadow: shadows[index], orbit: createOrbit(index), position: heroPositions[index],
    hovered: false, focused: false, elevation: 0,
    motion: null as Animation | null, projection: null as Animation | null,
  }));
  type Node = typeof nodes[number];
  const held = (node: Node) => node.hovered || node.focused;
  function update(node: Node) {
    const poses = rebaseOrbit(node.orbit, held(node), Number(node.motion?.currentTime ?? 0));
    const floats = poses.map((pose, index) => ({ offset: index / STEPS,
      transform: `translate3d(0,${pose.y * height * .025}px,0) rotate(${pose.r}deg)` }));
    const projections = poses.map((pose, index) => ({ offset: index / STEPS,
      transform: `translate3d(${pose.y * height * .0075}px,0,0) scale(${1 - pose.y * .02},${1 - pose.y * .05})`,
      opacity: (.22 + node.position.depth * .20) * (1 - node.elevation * .4) * (1 + pose.y * .08),
    }));
    const timing: OptionalEffectTiming = { duration: node.orbit.cycle, iterations: node.orbit.releasing ? 1 : Infinity, easing: 'linear', fill: 'both' };
    if (node.motion && node.projection) {
      (node.motion.effect as KeyframeEffect).setKeyframes(floats);
      (node.projection.effect as KeyframeEffect).setKeyframes(projections);
      node.motion.effect?.updateTiming(timing);
      node.projection.effect?.updateTiming(timing);
      node.motion.currentTime = 0;
      node.projection.currentTime = 0;
    } else {
      node.motion = node.figure.animate(floats, timing);
      node.projection = node.shadow.animate(projections, timing);
      node.motion.onfinish = () => {
        if (!disposed && node.orbit.releasing) { update(node); sync(); }
      };
    }
  }
  function sync() {
    if (disposed) return;
    const stopped = paused || reduced.matches || document.hidden || !inView;
    stage.classList.toggle('is-sleeping', stopped);
    nodes.forEach(node => {
      node.figure.classList.toggle('is-active', held(node));
      // A paused/reduced-motion display must remain still even on interaction.
      if (!stopped && node.motion && node.orbit.held !== held(node)) update(node);
      for (const animation of [node.motion, node.projection]) {
        if (!animation) continue;
        if (stopped) { if (animation.playState !== 'paused') animation.pause(); }
        else if (animation.playState !== 'running') animation.play();
      }
    });
  }
  function layout(w: number, h: number) {
    if (disposed || !w || !h || (w === width && h === height)) return;
    width = w; height = h;
    nodes.forEach(node => {
      const p = node.position, image = node.figure.querySelector('img')!;
      const cigarWidth = w * p.w / 100;
      const groundY = h * (.78 + p.depth * .185);
      node.elevation = Math.max(0, groundY - h * p.y / 100 - cigarWidth * image.height / image.width / 2) / h;
      const shadowWidth = cigarWidth * (.75 + node.elevation * .20);
      const shadowHeight = h * (.035 + node.elevation * .022);
      Object.assign(node.shadow.style, { width: `${shadowWidth}px`, height: `${shadowHeight}px`,
        left: `${w * p.x / 100 + (cigarWidth - shadowWidth) / 2 - node.elevation * h * .09}px`,
        top: `${groundY - shadowHeight / 2}px` });
      update(node);
    });
    sync();
  }
  nodes.forEach(node => {
    const enter = (event: PointerEvent) => { if (event.pointerType === 'mouse') { node.hovered = true; sync(); } };
    const leave = () => { node.hovered = false; sync(); };
    const focus = () => { node.focused = true; sync(); };
    const blur = () => { node.focused = false; sync(); };
    node.figure.addEventListener('pointerenter', enter);
    node.figure.addEventListener('pointerleave', leave);
    node.figure.addEventListener('focusin', focus);
    node.figure.addEventListener('focusout', blur);
    removers.push(() => {
      node.figure.removeEventListener('pointerenter', enter);
      node.figure.removeEventListener('pointerleave', leave);
      node.figure.removeEventListener('focusin', focus);
      node.figure.removeEventListener('focusout', blur);
    });
  });
  const resize = new ResizeObserver(entries => layout(entries[0].contentRect.width, entries[0].contentRect.height));
  const intersection = new IntersectionObserver(entries => { inView = entries[0].isIntersecting; sync(); });
  resize.observe(stage);
  intersection.observe(stage);
  reduced.addEventListener('change', sync);
  document.addEventListener('visibilitychange', sync);
  layout(stage.clientWidth, stage.clientHeight);
  stage.dataset.motionReady = 'true';
  return {
    setPaused(value: boolean) { paused = value; sync(); },
    destroy() {
      disposed = true;
      resize.disconnect(); intersection.disconnect();
      reduced.removeEventListener('change', sync);
      document.removeEventListener('visibilitychange', sync);
      removers.forEach(remove => remove());
      nodes.forEach(node => {
        if (node.motion) node.motion.onfinish = null;
        node.motion?.cancel(); node.projection?.cancel();
        node.figure.classList.remove('is-active');
      });
      delete stage.dataset.motionReady;
      stage.classList.remove('is-sleeping');
    },
  };
}
