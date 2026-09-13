(function () {
  var bar = document.getElementById('filter-bar');
  var grid = document.getElementById('card-grid');
  if (!grid) return;

  var cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
  var searchInput = document.getElementById('search-input');
  var clearBtn = document.getElementById('clear-filters');
  var noResults = document.getElementById('no-results');

  // active[group] = Set of selected term slugs
  var active = {};

  function applyFilters() {
    var query = (searchInput && searchInput.value || '').trim().toLowerCase();
    var anyActive = Object.keys(active).some(function (k) { return active[k].size > 0; });
    if (clearBtn) clearBtn.hidden = !(anyActive || query);

    var visibleCount = 0;
    cards.forEach(function (card) {
      var visible = true;
      Object.keys(active).forEach(function (group) {
        var wanted = active[group];
        if (!wanted || wanted.size === 0) return;
        var have = (card.getAttribute('data-' + group) || '').split(/\s+/).filter(Boolean);
        var match = have.some(function (v) { return wanted.has(v); });
        if (!match) visible = false;
      });
      if (visible && query) {
        var hay = card.getAttribute('data-search') || '';
        if (hay.indexOf(query) === -1) visible = false;
      }
      card.style.display = visible ? '' : 'none';
      if (visible) visibleCount++;
    });

    if (noResults) noResults.hidden = visibleCount !== 0;
  }

  if (bar) {
    bar.addEventListener('click', function (e) {
      var pill = e.target.closest('.pill--filter');
      if (!pill || !bar.contains(pill)) return;
      e.preventDefault();
      var group = pill.getAttribute('data-tax');
      var term = pill.getAttribute('data-term');
      if (!group || !term) return;
      if (!active[group]) active[group] = new Set();
      if (active[group].has(term)) {
        active[group].delete(term);
        pill.classList.remove('active');
      } else {
        active[group].add(term);
        pill.classList.add('active');
      }
      applyFilters();
    });
  }

  if (searchInput) {
    searchInput.addEventListener('input', applyFilters);
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      Object.keys(active).forEach(function (k) { active[k].clear(); });
      if (searchInput) searchInput.value = '';
      if (bar) bar.querySelectorAll('.pill--filter.active').forEach(function (p) { p.classList.remove('active'); });
      applyFilters();
    });
  }
})();
