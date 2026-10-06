/* ============================================================================
   Prototype interaction layer. Plain ES5-ish JS, no network, no build step.
   Everything it does is a real DOM change you can see in the frame.
   ========================================================================== */
(function () {
  'use strict';

  var root = document.documentElement;

  /* tab id in the console chrome -> prototype screen id */
  var TAB = {
    clock: 'clock',
    tonight: 'tonight',
    records: 'records',
    vision: 'vision',
    players: 'regulars',
    status: 'backroom'
  };

  /* screen id -> the frame the deck shows first for that screen */
  var DECKS = ['tonight', 'registration', 'tonight-draw', 'records', 'records-review',
    'regulars', 'vision', 'clock', 'backroom'];

  var state = { screen: 'tonight', lang: 'en', theme: 'dark', gallery: false };

  function all(sel, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(sel));
  }

  function frames() {
    return all('.pf-frame');
  }

  function frameFor(screen) {
    return document.querySelector('.pf-frame[data-screen="' + screen + '"][data-lang="' + state.lang + '"]');
  }

  /* which console tab a frame belongs to */
  function tabOf(f) {
    var own = f.getAttribute('data-tab-of');
    if (own) { return own; }
    var s = f.getAttribute('data-screen');
    for (var k in TAB) { if (TAB[k] === s) { return k; } }
    return '';
  }

  /* ---------------------------------------------------------------- paint */
  function paint() {
    root.setAttribute('data-theme', state.theme);
    root.setAttribute('data-lang', state.lang);
    root.setAttribute('lang', state.lang === 'zh' ? 'zh-Hans' : 'en');
    document.body.classList.toggle('pf-gallery', state.gallery);

    frames().forEach(function (f) {
      var sameLang = f.getAttribute('data-lang') === state.lang;
      var show = sameLang && (state.gallery || f.getAttribute('data-screen') === state.screen);
      f.classList.toggle('is-on', show);
    });

    all('[data-pf-go]').forEach(function (b) {
      b.classList.toggle('is-on', b.getAttribute('data-pf-go') === state.screen);
    });
    all('[data-pf-lang]').forEach(function (b) {
      b.classList.toggle('is-on', b.getAttribute('data-pf-lang') === state.lang);
    });
    all('[data-pf-theme]').forEach(function (b) {
      b.classList.toggle('is-on', b.getAttribute('data-pf-theme') === state.theme);
    });
    all('[data-pf-all]').forEach(function (b) {
      b.classList.toggle('is-on', state.gallery);
    });

    /* the console's own language and theme chips follow the prototype */
    all('.pf-canvas [data-lang]').forEach(function (b) {
      var on = b.getAttribute('data-lang') === state.lang;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    all('.pf-canvas [data-theme]').forEach(function (b) {
      var on = b.getAttribute('data-theme') === state.theme;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    /* keep the console's active tab in step with the frame that is showing */
    var cur = frameFor(state.screen);
    var curTab = cur ? tabOf(cur) : '';
    all('.pf-canvas [data-tab]').forEach(function (b) {
      var on = b.getAttribute('data-tab') === curTab;
      b.classList.toggle('active', on);
      b.setAttribute('aria-current', on ? 'page' : 'false');
    });

    closeAll();
  }

  /* scroll the deck to a frame without scrollIntoView(), which would yank an
     embedding page when the artifact is shown through an iframe. The sticky
     deck keeps its own height clear so a frame never lands under it. */
  function scrollToFrame(f) {
    if (!f) { return; }
    var deck = document.querySelector('.pf-deck');
    var off = (deck ? deck.getBoundingClientRect().height : 0) + 14;
    var box = f.getBoundingClientRect();
    var top = box.top + (window.pageYOffset || document.documentElement.scrollTop || 0) - off;
    window.scrollTo({ top: top < 0 ? 0 : top, behavior: 'smooth' });
  }

  function setScreen(id) {
    state.screen = id;
    paint();
    scrollToFrame(frameFor(id));
  }

  /* ------------------------------------------------------------- overlays */
  /* a dialog lives inside the frame that opens it, so two frames can hold
     their own copy of the same dialog and both stay interactive */
  function overlay(name, from) {
    var host = from && from.closest ? from.closest('.pf-frame') : null;
    if (host) {
      var own = host.querySelector('.pf-overlay[data-pf-overlay="' + name + '"]');
      if (own) { return own; }
    }
    return document.querySelector('.pf-frame.is-on .pf-overlay[data-pf-overlay="' + name + '"]')
      || document.querySelector('.pf-overlay[data-pf-overlay="' + name + '"]');
  }

  function openOverlay(name, from) {
    closeAll();
    var o = overlay(name, from);
    if (o) {
      o.classList.add('is-on');
      var first = o.querySelector('input,select,button');
      if (first && first.focus) { first.focus(); }
    }
  }

  function closeAll() {
    all('.pf-overlay.is-on').forEach(function (o) { o.classList.remove('is-on'); });
  }

  /* ------------------------------------------------------------- scrubber */
  /* the transport row appears on the review workbench and on the livestream
     panel, so every frame that carries one gets wired */
  function wireScrubber() {
    all('.pf-frame').forEach(function (f) {
      var scrub = f.querySelector('#vs-scrub');
      var index = f.querySelector('#vs-frame-index');
      var facts = f.querySelector('#vs-facts');
      var edge = f.querySelector('#vs-edge');
      var marks = f.querySelector('#vs-marks');
      var identity = f.querySelector('#vs-identity');
      var rail = f.querySelector('#vs-cues');
      if (!scrub) { return; }
      var FPS = 29.993;

      function hms(s) {
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        var sec = s % 60;
        return h + ':' + (m < 10 ? '0' : '') + m + ':' + (sec < 10 ? '0' : '') + sec.toFixed(1);
      }

      function render() {
        var t = parseFloat(scrub.value) || 0;
        var frame = Math.round(t * FPS);
        var pct = ((t - scrub.min) / (scrub.max - scrub.min)) * 100;
        /* the row carries one shot clock; the facts line repeats it, so both are
           driven from the same position on the scrubber */
        var left = 30 - Math.round(t % 30);
        if (index) { index.value = String(frame); }
        if (edge) { edge.style.left = pct.toFixed(2) + '%'; }
        if (facts) {
          facts.textContent = 'broadcast time ' + hms(t) + ' · shot clock ' + left + 's · overlays ON';
        }
        all('.vs-clock .clock', f).forEach(function (c) {
          c.textContent = '0:' + (left < 10 ? '0' : '') + left;
          c.classList.toggle('low', left <= 5);
        });
        if (identity) {
          identity.textContent = 'Source · tw-2890514774 · ' + Math.round(t) + ' s · ' + FPS + ' fps';
        }
        if (marks) {
          marks.style.backgroundPosition = pct.toFixed(2) + '% 0';
        }
      }

      scrub.addEventListener('input', render);
      scrub.addEventListener('change', render);

      all('[data-vs-action="step"]', f).forEach(function (b) {
        b.addEventListener('click', function () {
          var step = parseFloat(b.getAttribute('data-vs-value')) || 1;
          scrub.value = String(Math.min(parseFloat(scrub.max), Math.max(0, (parseFloat(scrub.value) || 0) + step)));
          render();
        });
      });
      if (index) {
        index.addEventListener('input', function () {
          var fr = parseFloat(index.value);
          if (!isNaN(fr)) { scrub.value = String(fr / FPS); render(); }
        });
      }
      if (rail) {
        rail.addEventListener('click', function (e) {
          var item = e.target.closest ? e.target.closest('.vs-item') : null;
          if (!item) { return; }
          all('.vs-item', rail).forEach(function (x) { x.classList.remove('on'); });
          item.classList.add('on');
          var mono = item.querySelector('.vs-mono');
          if (facts && mono) {
            facts.textContent = 'cue ' + mono.textContent.trim() + ' · overlays ON';
          }
        });
      }
      render();
    });
  }

  /* --------------------------------------------------------- bracket step */
  var CARD_STATES = [
    { cls: ' pending', status: 'scheduled', badge: 'saving…', pending: true, won: false, scores: ['0', '0'] },
    { cls: '', status: 'scheduled', badge: 'Racked', pending: false, won: false, scores: ['0', '0'] },
    { cls: ' live', status: 'live', badge: 'On table', pending: false, won: false, scores: ['0', '0'] },
    { cls: ' held', status: 'delayed', badge: 'Delayed', pending: false, won: false, scores: ['0', '0'] },
    { cls: '', status: 'bye', badge: 'Bye', pending: false, won: false, scores: ['', ''] },
    { cls: '', status: 'complete', badge: 'Signed', pending: false, won: true, scores: ['1', '0'] }
  ];

  /* the badge copy follows the console's own dictionary */
  var BADGE = {
    en: { scheduled: 'Racked', live: 'On table', delayed: 'Delayed', bye: 'Bye', complete: 'Signed', saving: 'saving…' },
    zh: { scheduled: '已排定', live: '进行中', delayed: '延迟', bye: '轮空', complete: '已签', saving: '保存中…' }
  };

  function lang() {
    return document.documentElement.getAttribute('data-lang') === 'zh' ? 'zh' : 'en';
  }

  function wireBracket() {
    all('[data-pf-step]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var host = btn.closest('.pf-frame');
        var card = host && host.querySelector('.bracket-card');
        if (!card) { return; }
        var next = (parseInt(btn.getAttribute('data-pf-step'), 10) + 1) % CARD_STATES.length;
        btn.setAttribute('data-pf-step', String(next));
        var s = CARD_STATES[next];
        var w = BADGE[lang()];
        var badgeText = s.pending ? w.saving : w[s.status];
        card.className = 'entry bracket-card' + s.cls;
        card.setAttribute('data-status', s.status);
        card.setAttribute('aria-busy', s.pending ? 'true' : 'false');

        var note = card.querySelector('.pending-note');
        if (s.pending && !note) {
          note = document.createElement('span');
          note.className = 'pending-note';
          note.setAttribute('role', 'status');
          note.textContent = w.saving;
          card.insertBefore(note, card.firstChild);
        } else if (!s.pending && note) {
          note.parentNode.removeChild(note);
        }

        var head = card.querySelector('.card-head');
        var badge = head && head.querySelector('.badge');
        if (badge) {
          badge.className = 'badge ' + (s.status === 'complete' ? 'complete' : s.status);
          badge.textContent = badgeText;
        }
        all('.card-side', card).forEach(function (side, i) {
          side.classList.toggle('won', s.won && i === 0);
          var sc = side.querySelector('.side-score');
          if (sc) { sc.textContent = s.scores[i]; }
        });
        var out = host.querySelector('[data-pf-step-out]');
        if (out) { out.textContent = s.status; }
      });
    });
  }

  /* ------------------------------------------------------------ shot clock */
  var clockTimer = null;

  function setClock(sec, host) {
    var txt = Math.floor(sec / 60) + ':' + (sec % 60 < 10 ? '0' : '') + Math.floor(sec % 60);
    all('[data-clock]', host || document).forEach(function (el) { el.textContent = txt; });
    all('[data-progress]', host || document).forEach(function (p) {
      p.style.transform = 'scaleX(' + (sec / 30).toFixed(4) + ')';
    });
  }

  function clockHost(el) {
    return (el.closest && (el.closest('.pf-canvas') || el.closest('.pf-frame'))) || document;
  }

  function wireClock() {
    document.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('[data-action="clock-toggle"],[data-action="clock-reset"],[data-action="clock-set"]') : null;
      if (!b) { return; }
      e.preventDefault();
      var act = b.getAttribute('data-action');
      var host = clockHost(b);
      if (act === 'clock-set') {
        clearInterval(clockTimer); clockTimer = null;
        setClock(parseInt(b.getAttribute('data-value'), 10), host);
        all('[data-action="clock-set"]', host).forEach(function (x) { x.classList.toggle('active', x === b); });
        return;
      }
      if (act === 'clock-reset') {
        clearInterval(clockTimer); clockTimer = null;
        setClock(30, host);
        var rl = host.querySelector('[data-action="clock-toggle"]');
        if (rl) { rl.textContent = 'Start'; }
        return;
      }
      if (clockTimer) {
        clearInterval(clockTimer);
        clockTimer = null;
        var lbl = b.querySelector('span') || b;
        lbl.textContent = 'Start';
      } else {
        var lbl2 = b.querySelector('span') || b;
        lbl2.textContent = 'Pause';
        var left = 30;
        var m = (host.querySelector('[data-clock]') || {}).textContent || '0:30';
        var parts = m.split(':');
        left = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
        clockTimer = setInterval(function () {
          left -= 1;
          setClock(left > 0 ? left : 0, host);
          if (left <= 0) {
            clearInterval(clockTimer); clockTimer = null;
            var t = host.querySelector('[data-action="clock-toggle"]');
            if (t) { (t.querySelector('span') || t).textContent = 'Start'; }
          }
        }, 1000);
      }
    });
  }

  /* ------------------------------------------- event format inside a frame */
  /* The late-join dialog draws its teammate fieldset only for a doubles
     event. The prototype control inside the same frame drives it. */
  function setFormat(host, fmt) {
    all('[data-pf-format]', host).forEach(function (b) {
      var on = b.getAttribute('data-pf-format') === fmt;
      b.classList.toggle('is-on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    all('[data-pf-doubles]', host).forEach(function (d) {
      d.classList.toggle('pf-hidden', fmt !== 'doubles');
    });
    all('.pf-canvas', host).forEach(function (c) {
      c.setAttribute('data-pf-format-state', fmt);
    });
  }

  function initFormats() {
    frames().forEach(function (f) {
      var on = f.querySelector('[data-pf-format].is-on');
      if (on) { setFormat(f, on.getAttribute('data-pf-format')); }
    });
  }

  /* ---------------------------------------------------------- delegation */
  document.addEventListener('click', function (e) {
    var el = e.target.closest ? e.target.closest('[data-pf-go],[data-pf-all],[data-pf-lang],[data-pf-theme],[data-pf-format],[data-tab],[data-theme],[data-lang],[data-action]') : null;
    if (!el) { return; }

    if (el.hasAttribute('data-pf-go')) {
      setScreen(el.getAttribute('data-pf-go'));
      return;
    }
    if (el.hasAttribute('data-pf-all')) {
      state.gallery = !state.gallery;
      paint();
      return;
    }
    if (el.hasAttribute('data-pf-lang')) {
      state.lang = el.getAttribute('data-pf-lang');
      paint();
      return;
    }
    if (el.hasAttribute('data-pf-theme')) {
      state.theme = el.getAttribute('data-pf-theme');
      paint();
      return;
    }
    if (el.hasAttribute('data-pf-format')) {
      var host = el.closest('.pf-frame') || document;
      setFormat(host, el.getAttribute('data-pf-format'));
      return;
    }
    if (el.hasAttribute('data-tab')) {
      var target = TAB[el.getAttribute('data-tab')];
      if (target) {
        e.preventDefault();
        if (state.gallery) {
          scrollToFrame(frameFor(target));
        } else {
          setScreen(target);
        }
      }
      return;
    }
    if (el.hasAttribute('data-theme')) {
      state.theme = el.getAttribute('data-theme');
      paint();
      return;
    }
    if (el.hasAttribute('data-lang')) {
      state.lang = el.getAttribute('data-lang');
      paint();
      return;
    }

    var action = el.getAttribute('data-action');
    switch (action) {
      case 'late-open':
        e.preventDefault(); openOverlay('late', el); break;
      case 'late-cancel':
        e.preventDefault(); closeAll(); break;
      case 'sources-open':
        e.preventDefault(); openOverlay('sources', el); break;
      case 'sources-close':
        e.preventDefault(); closeAll(); break;
      case 'select-player':
        e.preventDefault(); openOverlay('player', el); break;
      case 'open-add-player':
        e.preventDefault(); openOverlay('newplayer', el); break;
      case 'appearance-open':
        e.preventDefault(); openOverlay('appearance', el); break;
      case 'close-modal':
        e.preventDefault(); closeAll(); break;
      case 'backfill-open':
        e.preventDefault(); break;
      case 'tl-review':
      case 'vod-open':
        e.preventDefault(); setScreen('records-review'); break;
      default:
        break;
    }
  }, false);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeAll(); }
  }, false);

  var booted = false;

  function boot() {
    if (booted) { return; }
    booted = true;
    wireScrubber();
    wireBracket();
    wireClock();
    initFormats();
    paint();
    /* #frame-id or #frame-id@zh picks the frame that opens first, so a
       screenshot run can address one frame without clicking. */
    var hash = (window.location.hash || '').replace(/^#/, '');
    if (hash) {
      var bits = hash.split('@');
      if (bits[1] === 'zh' || bits[1] === 'en') { state.lang = bits[1]; }
      if (document.querySelector('.pf-frame[data-screen="' + bits[0] + '"]')) { state.screen = bits[0]; }
      paint();
    }
  }

  if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
}());
