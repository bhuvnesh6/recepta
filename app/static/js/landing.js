document.addEventListener('DOMContentLoaded', function () {
  // ---------- Mobile nav toggle ----------
  var burger = document.getElementById('lp-burger');
  var navLinks = document.getElementById('lp-nav-links');
  if (burger && navLinks) {
    burger.addEventListener('click', function () { navLinks.classList.toggle('open'); });
    navLinks.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () { navLinks.classList.remove('open'); });
    });
  }

  // ---------- Hero widget demo: loops through 4 phases forever ----------
  var bubble = document.getElementById('lp-demo-bubble');
  var panel = document.getElementById('lp-demo-panel');
  var greetingLine = document.getElementById('lp-demo-greeting');
  var statusLine = document.getElementById('lp-demo-status');
  var leadCard = document.getElementById('lp-demo-lead-card');

  if (!bubble || !panel) return;

  var GREETING = "Hi! How can I help you today?";

  function typeText(el, text, speed, done) {
    el.textContent = '';
    var caret = document.createElement('span');
    caret.className = 'lp-demo-caret';
    el.appendChild(document.createTextNode(''));
    el.appendChild(caret);
    var i = 0;
    var timer = setInterval(function () {
      el.textContent = text.slice(0, i);
      el.appendChild(caret);
      i++;
      if (i > text.length) {
        clearInterval(timer);
        caret.remove();
        if (done) done();
      }
    }, speed);
    return timer;
  }

  function resetDemo() {
    panel.classList.remove('show');
    statusLine.classList.remove('show');
    leadCard.classList.remove('show');
    greetingLine.textContent = '';
  }

  function runLoop() {
    resetDemo();

    // Phase 1: bubble pulses alone (idle)
    setTimeout(function () {
      // Phase 2: panel pops open, greeting types out
      panel.classList.add('show');
      typeText(greetingLine, GREETING, 28, function () {
        // Phase 3: "speaking" indicator (mic pulse)
        setTimeout(function () {
          statusLine.classList.add('show');
          setTimeout(function () {
            statusLine.classList.remove('show');
            // Phase 4: lead captured card slides in
            leadCard.classList.add('show');
            setTimeout(runLoop, 2200);
          }, 1600);
        }, 500);
      });
    }, 1400);
  }

  runLoop();

  // ---------- Smooth-scroll for in-page nav anchors ----------
  document.querySelectorAll('a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var target = document.querySelector(a.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
});