(function () {
  'use strict';

  var root = document.getElementById('startup-loader');
  if (!root || window.CDTStartup) return;

  var mark = root.querySelector('.cdt-startup__logo');
  var status = root.querySelector('.cdt-startup__status');
  var retry = root.querySelector('.cdt-startup__retry');
  var surface = root.querySelector('.cdt-startup__surface');
  var motionStart = null;
  var cycleDuration = 2580;
  var logoReady = false;
  var readyRequested = false;
  var state = 'loading';
  var handoffTimer;
  var slowTimer;
  var observer;

  function reducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function clearTimers() {
    window.clearTimeout(handoffTimer);
    window.clearTimeout(slowTimer);
  }

  function setStatus(text) {
    if (state === 'loading' || state === 'failed') {
      status.querySelector('.cdt-startup__status-label').textContent = String(text);
    }
  }

  function hasPendingReactLoader() {
    return Boolean(document.querySelector('#root .cdt-loader'));
  }

  function finish() {
    if (state !== 'docking') return;
    state = 'ready';
    root.remove();
    document.body.classList.remove('cdt-starting', 'cdt-revealing');
    document.documentElement.removeAttribute('data-cdt-starting');
    document.documentElement.removeAttribute('data-cdt-app-ready');
    observer && observer.disconnect();
  }

  function dock() {
    if (state !== 'loading' || !readyRequested || hasPendingReactLoader()) return;
    clearTimers();
    state = 'docking';
    root.dataset.phase = 'docking';
    root.inert = true;
    root.setAttribute('aria-hidden', 'true');
    root.setAttribute('aria-busy', 'false');
    retry.hidden = true;

    document.body.classList.add('cdt-revealing');

    if (reducedMotion() || document.hidden || !mark.animate) {
      finish();
      return;
    }

    var target = document.querySelector('[data-startup-logo-target]');
    var backdrop = surface.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: 400, easing: 'ease-out', fill: 'both' }
    );
    status.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration: 140, easing: 'ease-out', fill: 'both' }
    );

    if (!target) {
      backdrop.finished.then(finish, finish);
      return;
    }

    var from = mark.getBoundingClientRect();
    var box = target.getBoundingClientRect();
    var targetHeight = box.width * 525 / 640;
    var targetTop = box.top + (box.height - targetHeight) / 2;
    var scale = box.width / from.width;

    mark.src = mark.dataset.staticSrc;
    mark.classList.add('cdt-startup__logo--docking');
    var flight = mark.animate(
      [
        { transform: 'translate(0, 0) scale(1)' },
        { transform: 'translate(' + (box.left - from.left) + 'px, ' + (targetTop - from.top) + 'px) scale(' + scale + ')' }
      ],
      { duration: 400, easing: 'ease-out', fill: 'both' }
    );
    flight.finished.then(finish, finish);
  }

  function attemptReady() {
    if (!readyRequested || !logoReady || state !== 'loading' || hasPendingReactLoader()) return;
    window.cancelAnimationFrame(attemptReady.frame);
    window.clearTimeout(handoffTimer);
    attemptReady.frame = window.requestAnimationFrame(function () {
      attemptReady.frame = window.requestAnimationFrame(function () {
        if (hasPendingReactLoader()) return;
        if (reducedMotion()) {
          dock();
          return;
        }
        var elapsed = performance.now() - motionStart;
        var wait = Math.max(cycleDuration - elapsed, 0);
        handoffTimer = window.setTimeout(dock, wait);
      });
    });
  }

  function revealLogo() {
    if (logoReady) return;
    logoReady = true;
    motionStart = performance.now();
    root.dataset.logoReady = 'true';
    attemptReady();
  }

  function prepareLogo() {
    if (!mark.naturalWidth) return;
    if (typeof mark.decode === 'function') {
      mark.decode().then(revealLogo, revealLogo);
      return;
    }
    revealLogo();
  }

  function ready() {
    if (state !== 'loading') return;
    readyRequested = true;
    attemptReady();
  }

  function fail() {
    if (state !== 'loading') return;
    clearTimers();
    state = 'failed';
    root.dataset.phase = 'failed';
    mark.src = mark.dataset.staticSrc;
    root.setAttribute('aria-busy', 'false');
    setStatus('内容加载失败，请重试');
    retry.hidden = false;
  }

  function destroy() {
    if (state === 'destroyed') return;
    clearTimers();
    observer && observer.disconnect();
    state = 'destroyed';
    root.remove();
    document.body.classList.remove('cdt-starting', 'cdt-revealing');
    document.documentElement.removeAttribute('data-cdt-starting');
    document.documentElement.removeAttribute('data-cdt-app-ready');
  }

  retry.addEventListener('click', function () { window.location.reload(); });
  mark.addEventListener('load', prepareLogo);
  mark.src = mark.dataset.motionSrc;
  if (mark.complete) prepareLogo();
  observer = new MutationObserver(attemptReady);
  observer.observe(document.getElementById('root'), { childList: true, subtree: true });
  slowTimer = window.setTimeout(function () {
    if (state !== 'loading') return;
    setStatus('加载时间较长，请稍候');
    retry.hidden = false;
  }, 10000);

  window.CDTStartup = Object.freeze({
    init: function () { return window.CDTStartup; },
    ready: ready,
    fail: fail,
    setStatus: setStatus,
    destroy: destroy
  });
  window.addEventListener('cdt:app-ready', ready, { once: true });
  if (document.documentElement.dataset.cdtAppReady === 'true') ready();
}());
