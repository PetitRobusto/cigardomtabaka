// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createOrbit, mountHeroMotion, orbitPose, rebaseOrbit } from './HomeHero.motion';
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.replaceChildren(); });

describe('pose continuity', () => {
  it.each([0, 1, 2, 3, 4])('anchors cigar %i and resumes its original clock after long hover', index => {
    for (const fraction of [.08, .31, .59, .88]) for (const heldCycles of [.17, 1.63, 12.4]) {
      const orbit = createOrbit(index);
      rebaseOrbit(orbit, false, 0);
      const before = orbitPose(orbit, orbit.cycle * fraction);
      rebaseOrbit(orbit, true, orbit.cycle * fraction);
      expect(orbitPose(orbit, 0)).toEqual(before);
      const phase = orbit.phase;
      const bob = orbitPose(orbit, orbit.cycle / 4);
      expect(bob.y - before.y).toBeCloseTo(.22, 5);
      expect(bob.r - before.r).toBeCloseTo(.35, 5);
      const release = orbitPose(orbit, orbit.cycle * heldCycles);
      rebaseOrbit(orbit, false, orbit.cycle * heldCycles);
      expect(orbit.phase).toBe(phase);
      expect(orbitPose(orbit, 0).y).toBeCloseTo(release.y, 10);
      expect(orbitPose(orbit, 0).r).toBeCloseTo(release.r, 10);
      expect(Math.abs(orbitPose(orbit, orbit.cycle * .01).y - release.y)).toBeLessThan(.065);
      const finish = orbitPose(orbit, orbit.cycle);
      rebaseOrbit(orbit, false, orbit.cycle);
      expect(orbitPose(orbit, 0).y).toBeCloseTo(finish.y, 10);
      expect(orbit.releasing).toBe(false);
    }
  });
  it('preserves the held midpoint when rebuilding after resize', () => {
    const orbit = createOrbit(2);
    rebaseOrbit(orbit, false, 0); rebaseOrbit(orbit, true, 2300);
    const anchor = { ...orbit.anchor }, before = orbitPose(orbit, 1500);
    rebaseOrbit(orbit, true, 1500);
    expect(orbit.anchor).toEqual(anchor);
    expect(orbitPose(orbit, 0).y).toBeCloseTo(before.y, 3);
  });
});

describe('lifecycle', () => {
  it('pauses for accessibility/visibility and disposes observers, listeners and animations', () => {
    document.body.innerHTML = '<div id="stage"><span class="store-home-hero__shadow"></span><figure class="store-home-hero__cigar"><a href="/catalog"><img width="997" height="139" /></a></figure></div>';
    const stage = document.getElementById('stage')!;
    Object.defineProperties(stage, { clientWidth: { value: 500 }, clientHeight: { value: 525 } });
    const resizeDisconnect = vi.fn(), intersectionDisconnect = vi.fn();
    vi.stubGlobal('ResizeObserver', class { observe = vi.fn(); disconnect = resizeDisconnect; });
    let intersect: (entries: { isIntersecting: boolean }[]) => void = () => {};
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: typeof intersect) { intersect = callback; }
      observe = vi.fn(); disconnect = intersectionDisconnect;
    });
    const media = new EventTarget() as EventTarget & { matches: boolean };
    media.matches = false;
    vi.stubGlobal('matchMedia', () => media);
    const createAnimation = () => {
      const animation = { currentTime: 0, playState: 'running',
        pause: vi.fn(() => { animation.playState = 'paused'; }),
        play: vi.fn(() => { animation.playState = 'running'; }), cancel: vi.fn(),
        effect: { setKeyframes: vi.fn(), updateTiming: vi.fn() }, onfinish: null as (() => void) | null };
      return animation;
    };
    const animations: ReturnType<typeof createAnimation>[] = [];
    const animate = vi.fn(() => { const animation = createAnimation(); animations.push(animation); return animation; });
    Object.defineProperty(stage, 'animate', { value: animate });
    stage.querySelectorAll<HTMLElement>('figure, span').forEach(element => Object.defineProperty(element, 'animate', { value: animate }));
    const controller = mountHeroMotion(stage)!;
    expect(animations).toHaveLength(2);
    controller.setPaused(true);
    expect(animations.every(animation => animation.playState === 'paused')).toBe(true);
    controller.setPaused(false);
    intersect([{ isIntersecting: false }]);
    expect(animations.every(animation => animation.playState === 'paused')).toBe(true);
    intersect([{ isIntersecting: true }]);
    expect(animations.every(animation => animation.playState === 'running')).toBe(true);
    media.matches = true; media.dispatchEvent(new Event('change'));
    stage.querySelector('a')!.focus();
    expect(animations.every(animation => animation.playState === 'paused')).toBe(true);
    expect(animations[0].effect.setKeyframes).not.toHaveBeenCalled();
    media.matches = false; media.dispatchEvent(new Event('change'));
    expect(animations[0].effect.setKeyframes).toHaveBeenCalledOnce();
    vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(animations.every(animation => animation.playState === 'paused')).toBe(true);
    controller.destroy();
    expect(resizeDisconnect).toHaveBeenCalledOnce();
    expect(intersectionDisconnect).toHaveBeenCalledOnce();
    expect(animations.every(animation => animation.cancel.mock.calls.length === 1 && animation.onfinish === null)).toBe(true);
    expect(stage.dataset.motionReady).toBeUndefined();
    const calls = animations[0].effect.setKeyframes.mock.calls.length;
    media.dispatchEvent(new Event('change')); document.dispatchEvent(new Event('visibilitychange'));
    expect(animations[0].effect.setKeyframes.mock.calls.length).toBe(calls);
  });
});
