(function () {
  'use strict';

  var root = document.getElementById('startup-loader');
  if (!root || window.CDTStartup) return;

  var mark = root.querySelector('.cdt-startup__logo');
  var status = root.querySelector('.cdt-startup__status');
  var retry = root.querySelector('.cdt-startup__retry');
  var surface = root.querySelector('.cdt-startup__surface');
  var appRoots = Array.prototype.slice.call(document.querySelectorAll('#root, #store-root'));
  if (!mark || !status || !retry || !surface || !appRoots.length) return;
  // This script also starts before React in the static/Django shells. Keep its
  // small recovery dictionary aligned with customerMessages (covered by tests).
  var messages = {
    zh: { intro: '页面内容加载中…', loading: '页面内容加载中…', failed: '数据加载失败', retry: '重新加载' },
    ru: { intro: 'Загрузка страницы…', loading: 'Загрузка страницы…', failed: 'Не удалось загрузить данные', retry: 'Повторить' },
    en: { intro: 'Loading page…', loading: 'Loading page…', failed: 'Could not load data', retry: 'Reload' }
  };

  function resolveLocale() {
    // SSR knows the actual page language; a saved preference cannot override it.
    if (Object.prototype.hasOwnProperty.call(messages, root.dataset.locale)) return root.dataset.locale;
    var route = window.location.pathname.match(/^\/(en|ru)(?:\/|$)/);
    if (route) return route[1];
    // The legacy customer catalogue follows saved/browser preferences. Other
    // unprefixed pages (including staff pages) use Chinese.
    if (/^\/(?:brand\/[^/]+\/?)?$/.test(window.location.pathname)) {
      var runtime = document.getElementById('cdt-app-runtime-config');
      try { if (runtime && JSON.parse(runtime.textContent).storefrontEnabled) return 'zh'; } catch { /* Fall back to legacy preferences. */ }
      try {
        var saved = window.localStorage.getItem('cdt.customer.language');
        if (Object.prototype.hasOwnProperty.call(messages, saved)) return saved;
      } catch { /* Browser storage can be disabled. */ }
      var languages = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language];
      for (var i = 0; i < languages.length; i++) {
        var base = String(languages[i]).toLowerCase().split('-')[0];
        if (Object.prototype.hasOwnProperty.call(messages, base)) return base;
      }
      return 'en';
    }
    return 'zh';
  }

  var locale = resolveLocale();
  var copy = messages[locale];
  root.lang = locale === 'zh' ? 'zh-CN' : locale;
  root.dataset.locale = locale;
  root.dataset.slowText = copy.loading;
  root.dataset.failedText = copy.failed;
  root.dataset.retryText = copy.retry;
  root.setAttribute('aria-label', copy.loading);
  status.querySelector('.cdt-startup__status-label').textContent = copy.intro;
  retry.textContent = copy.retry;
  // The SSR overlay stays hidden unless this script is available and runs.
  root.hidden = false;
  document.documentElement.dataset.cdtStarting = 'true';
  document.body.classList.add('cdt-starting');
  var motionSrc = mark.dataset.motionSrc || mark.getAttribute('src');
  var staticSrc = mark.dataset.staticSrc;
  var motionStart = null;
  var cycleDuration = 2580;
  var logoReady = false;
  var usingStaticLogo = false;
  var logoUnavailable = false;
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
    return Boolean(document.querySelector('#root .cdt-loader, #store-root .cdt-loader'));
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

    if (!target || logoUnavailable) {
      backdrop.finished.then(finish, finish);
      return;
    }

    var from = mark.getBoundingClientRect();
    var box = target.getBoundingClientRect();
    var targetHeight = box.width * 525 / 640;
    var targetTop = box.top + (box.height - targetHeight) / 2;
    var scale = box.width / from.width;

    if (staticSrc) mark.src = staticSrc;
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

  function revealLogo(skipMotionCycle) {
    if (logoReady) return;
    logoReady = true;
    motionStart = performance.now() - (skipMotionCycle ? cycleDuration : 0);
    root.dataset.logoReady = 'true';
    attemptReady();
  }

  function prepareLogo() {
    if (!mark.naturalWidth) return;
    revealLogo(usingStaticLogo);
  }

  function prepareCompleteLogo() {
    if (!mark.complete) return;
    if (mark.naturalWidth) prepareLogo();
    else handleLogoError();
  }

  function handleLogoError() {
    if (!usingStaticLogo && staticSrc) {
      usingStaticLogo = true;
      mark.src = staticSrc;
      prepareCompleteLogo();
      return;
    }
    logoUnavailable = true;
    mark.style.visibility = 'hidden';
    revealLogo(true);
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
    setStatus(root.dataset.failedText || copy.failed);
    retry.textContent = root.dataset.retryText || retry.textContent;
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
  mark.addEventListener('error', handleLogoError);
  if (motionSrc) {
    if (mark.getAttribute('src') !== motionSrc) mark.src = motionSrc;
    prepareCompleteLogo();
  } else {
    handleLogoError();
  }
  observer = new MutationObserver(attemptReady);
  appRoots.forEach(function (appRoot) {
    observer.observe(appRoot, { childList: true, subtree: true });
  });
  slowTimer = window.setTimeout(function () {
    if (state !== 'loading') return;
    setStatus(root.dataset.slowText || copy.loading);
    retry.textContent = root.dataset.retryText || retry.textContent;
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
