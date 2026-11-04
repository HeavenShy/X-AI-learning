// 一话一懂 原型公共脚本：填充重复的系统栏、标签栏、拟声词爆炸框，以及少量交互
(function () {

  // 公共图标
  var st = ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
  function S(id, vb, body) { return '<symbol id="' + id + '" viewBox="' + vb + '">' + body + '</symbol>'; }
  var sprite = [
    S('coin', '0 0 24 24', '<circle cx="12" cy="12" r="10" fill="#FFD21F" stroke="#000" stroke-width="2"/><circle cx="12" cy="12" r="6" fill="none" stroke="#000" stroke-width="1.5"/>'),
    S('xp', '0 0 24 24', '<path d="M13.5 2 L5 13.5 h6 L9.5 22 L19 10 h-6 Z" fill="#FFD21F" stroke="#000" stroke-width="2" stroke-linejoin="round"/>'),
    S('i-doc', '0 0 16 16', '<path d="M4 1.5h5l3 3V14.5H4z M9 1.5v3h3" fill="none" stroke="currentColor" stroke-width="1.6"/>'),
    S('i-link', '0 0 16 16', '<path d="M6.5 9.5l3-3 M7 4.5l1.5-1.5a2.5 2.5 0 013.5 3.5L10.5 8 M9 11.5L7.5 13a2.5 2.5 0 01-3.5-3.5L5.5 8" fill="none" stroke="currentColor" stroke-width="1.6"/>'),
    S('i-video', '0 0 16 16', '<rect x="1.5" y="3" width="13" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M6.5 6v4l3.5-2z" fill="currentColor"/>'),
    S('i-close', '0 0 18 18', '<path d="M3 3l12 12M15 3L3 15" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>'),
    S('i-back', '0 0 12 20', '<path d="M10 2L2 10l8 8" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'),
    S('i-warn', '0 0 18 18', '<circle cx="9" cy="9" r="8" fill="#E5322D"/><path d="M9 4.5v5.5" stroke="#fff" stroke-width="2" stroke-linecap="round"/><circle cx="9" cy="13" r="1.2" fill="#fff"/>'),
    S('i-ok', '0 0 22 22', '<circle cx="11" cy="11" r="10" fill="#14A160"/><path d="M6 11.5l3.2 3.2L16 8" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>'),
    S('i-folder', '0 0 24 24', '<path' + st + ' d="M3 6h6l2 2h10v11H3z"/>'),
    S('i-plus', '0 0 24 24', '<path' + st + ' d="M12 5v14M5 12h14"/>'),
    S('i-mic', '0 0 24 24', '<rect' + st + ' x="9" y="3" width="6" height="11" rx="3"/><path' + st + ' d="M5 11a7 7 0 0014 0 M12 18v3"/>'),
    S('i-play', '0 0 24 24', '<path d="M8 5v14l11-7z" fill="currentColor"/>'),
    S('i-image', '0 0 24 24', '<rect' + st + ' x="3" y="5" width="18" height="14"/><circle' + st + ' cx="9" cy="10" r="2"/><path' + st + ' d="M21 16l-5-5-8 8"/>'),
    S('i-trophy', '0 0 24 24', '<path' + st + ' d="M7 4h10v5a5 5 0 01-10 0z M7 6H4a3 3 0 003 4 M17 6h3a3 3 0 01-3 4 M12 14v4 M8 21h8"/>'),
    S('i-clock', '0 0 24 24', '<circle' + st + ' cx="12" cy="12" r="9"/><path' + st + ' d="M12 7v5l3 2"/>'),
    S('i-chart', '0 0 24 24', '<path' + st + ' d="M3 21h18 M6 17v-5 M11 17V7 M16 17v-8 M21 17V4"/>'),
    S('i-book', '0 0 24 24', '<path' + st + ' d="M4 5h6a2 2 0 012 2v13H6a2 2 0 01-2-2z M20 5h-6a2 2 0 00-2 2v13h6a2 2 0 002-2z"/>'),
    S('i-bell', '0 0 24 24', '<path' + st + ' d="M6 16v-5a6 6 0 0112 0v5l2 2H4z M10 21h4"/>'),
    S('i-tree', '0 0 24 24', '<path' + st + ' d="M12 6v14 M12 10H6v4 M12 15h6v4"/><rect' + st + ' x="9" y="2" width="6" height="4"/>'),
    S('i-cross-book', '0 0 24 24', '<path' + st + ' d="M5 3h14v18H5z M9 9l6 6 M15 9l-6 6"/>'),
    S('i-crown', '0 0 24 24', '<path' + st + ' d="M3 8l4 4 5-7 5 7 4-4-2 11H5z"/>'),
    S('i-lock', '0 0 24 24', '<rect' + st + ' x="5" y="11" width="14" height="10"/><path' + st + ' d="M8 11V8a4 4 0 018 0v3"/>'),
    S('i-search', '0 0 24 24', '<circle' + st + ' cx="11" cy="11" r="7"/><path' + st + ' d="M20 20l-4-4"/>'),
    S('i-share', '0 0 24 24', '<path' + st + ' d="M4 12v8h16v-8 M12 3v12 M7 8l5-5 5 5"/>'),
    S('i-chest', '0 0 24 24', '<path' + st + ' d="M3 10h18v10H3z M3 10l2-5h14l2 5 M12 10v10 M9 14h6"/>'),
    S('i-sound', '0 0 24 24', '<path' + st + ' d="M4 9v6h4l5 4V5L8 9z M16 9a4 4 0 010 6 M18.5 6.5a8 8 0 010 11"/>'),
    S('i-swords', '0 0 24 24', '<path' + st + ' d="M4 4l9 9 M4 4h4 M4 4v4 M20 4l-9 9 M20 4h-4 M20 4v4 M7 15l-3 3 2 2 3-3 M17 15l3 3-2 2-3-3"/>'),
    S('i-user', '0 0 24 24', '<circle' + st + ' cx="12" cy="8" r="4"/><path' + st + ' d="M4 21c1-5 4.5-7 8-7s7 2 8 7"/>'),
    S('i-gear', '0 0 24 24', '<circle' + st + ' cx="12" cy="12" r="3"/><path' + st + ' d="M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1L7 17 M17 7l2.1-2.1"/>'),
    S('i-upload', '0 0 24 24', '<path' + st + ' d="M12 16V4 M7 9l5-5 5 5 M4 16v4h16v-4"/>'),
    S('i-chat', '0 0 24 24', '<path' + st + ' d="M4 5h16v11H9l-5 4z"/>')
  ].join('');
  document.body.insertAdjacentHTML('afterbegin', '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>' + sprite + '</defs></svg>');

  // 原型文件导航
  var files = [['00', '设计规范', '00-style-board.html'], ['01', '核心闯关流程', '01-core-flow.html'], ['02', '多源输入与知识库', '02-input-and-library.html'], ['03', '学习后台与复盘', '03-review-and-stats.html'], ['04', '社交与会员', '04-social-and-vip.html']];
  document.querySelectorAll('.proto-nav[data-cur]').forEach(function (nav) {
    var cur = nav.getAttribute('data-cur');
    nav.innerHTML = files.map(function (f) { return '<a href="' + f[2] + '"' + (f[0] === cur ? ' aria-current="page"' : '') + '>' + f[0] + ' ' + f[1] + '</a>'; }).join('');
  });
  document.querySelectorAll('.statusbar:empty').forEach(function (el) {
    el.innerHTML = '<span>9:41</span><i></i>';
  });
  document.querySelectorAll('.capsule:empty').forEach(function (el) {
    el.innerHTML = '<i></i>';
  });

  var tabs = {
    '闯关': '<svg viewBox="0 0 26 26" fill="none" stroke="C" stroke-width="2.2" stroke-linejoin="round"><rect x="3" y="4" width="20" height="18" fill="F"/><path d="M13 4v18 M3 13h10"/></svg>',
    '复习': '<svg viewBox="0 0 26 26" fill="none" stroke="C" stroke-width="2.2" stroke-linecap="round"><circle cx="13" cy="13" r="9.5" fill="F"/><path d="M13 8v5l3.5 2.5"/></svg>',
    '我的': '<svg viewBox="0 0 26 26" fill="none" stroke="C" stroke-width="2.2" stroke-linecap="round"><circle cx="13" cy="9" r="4.5" fill="F"/><path d="M4.5 23c1-5 4.5-7 8.5-7s7.5 2 8.5 7"/></svg>'
  };
  document.querySelectorAll('nav.tabbar[data-on]').forEach(function (nav) {
    var on = nav.getAttribute('data-on');
    nav.innerHTML = Object.keys(tabs).map(function (k) {
      var active = k === on;
      var svg = tabs[k].replace('stroke="C"', 'stroke="' + (active ? '#000' : '#5E6670') + '"')
                       .replace('fill="F"', 'fill="' + (active ? '#FFD21F' : 'none') + '"');
      return '<a href="#"' + (active ? ' class="is-on" aria-current="page"' : '') + '>' + svg + k + '</a>';
    }).join('');
  });

  document.querySelectorAll('svg[data-burst]').forEach(function (svg) {
    var p = svg.getAttribute('data-burst').split(',').map(Number), n = p[0], R = p[1], r = p[2], pts = [];
    var vb = svg.viewBox.baseVal, cx = vb.width / 2, cy = vb.height / 2;
    for (var i = 0; i < n * 2; i++) {
      var rad = (i % 2 ? r : R) * (i % 4 === 0 ? 1 : .9), a = Math.PI * i / n - Math.PI / 2;
      pts.push((cx + rad * Math.cos(a) * 1.05).toFixed(1) + ',' + (cy + rad * Math.sin(a) * .85).toFixed(1));
    }
    var fill = svg.getAttribute('data-fill') || '#FFF4C4';
    svg.innerHTML = '<polygon points="' + pts.join(' ') + '" fill="' + fill + '" stroke="#000" stroke-width="2.5" stroke-linejoin="round"/>';
  });

  document.querySelectorAll('[data-replay]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var s = document.getElementById(btn.getAttribute('data-replay'));
      s.classList.remove('anim'); void s.offsetWidth; s.classList.add('anim');
    });
  });

  document.querySelectorAll('.cb-toggle').forEach(function (b) {
    b.addEventListener('click', function () {
      var open = b.getAttribute('aria-expanded') === 'true';
      b.setAttribute('aria-expanded', String(!open));
      b.textContent = open ? '展开' : '收起';
      b.closest('.caption-box').querySelector('.cb-body').hidden = open;
    });
  });

  document.querySelectorAll('[role="group"][data-single]').forEach(function (g) {
    g.querySelectorAll('button').forEach(function (b) {
      b.addEventListener('click', function () {
        g.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', 'false'); });
        b.setAttribute('aria-pressed', 'true');
      });
    });
  });

  // 小程序码占位：太阳码样式的放射点阵
  document.querySelectorAll('svg[data-qr]').forEach(function (svg) {
    var out = '<circle cx="50" cy="50" r="48" fill="#fff"/>', seed = 7;
    function rnd() { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; }
    for (var ring = 0; ring < 5; ring++) {
      var rr = 20 + ring * 6, count = 18 + ring * 6;
      for (var k = 0; k < count; k++) {
        if (rnd() < .38) continue;
        var a = 2 * Math.PI * k / count, x = 50 + rr * Math.cos(a), y = 50 + rr * Math.sin(a);
        out += '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="2.1" fill="#000"/>';
      }
    }
    [[22, 22], [78, 22], [22, 78]].forEach(function (c) {
      out += '<circle cx="' + c[0] + '" cy="' + c[1] + '" r="8" fill="#fff" stroke="#000" stroke-width="3"/><circle cx="' + c[0] + '" cy="' + c[1] + '" r="3.2" fill="#000"/>';
    });
    out += '<circle cx="50" cy="50" r="13" fill="#FFD21F" stroke="#000" stroke-width="2.5"/><text x="50" y="55" text-anchor="middle" font-size="12" font-family="ZCOOL QingKe HuangYou, sans-serif">懂</text>';
    svg.innerHTML = out;
  });
})();
