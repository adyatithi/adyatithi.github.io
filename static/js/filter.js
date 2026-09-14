(function () {
  var bar = document.getElementById('filter-bar');
  var grid = document.getElementById('card-grid');
  if (!grid) return;

  var searchInput = document.getElementById('search-input');
  var clearBtn = document.getElementById('clear-filters');
  var noResults = document.getElementById('no-results');

  var GROUPS = ['month', 'rashi', 'devata', 'tradition', 'tithi', 'nakshatra', 'category', 'tags'];

  // Parse each card's facet terms once up front.
  var cards = Array.prototype.slice.call(grid.querySelectorAll('.card')).map(function (el) {
    var terms = {};
    GROUPS.forEach(function (g) {
      terms[g] = (el.getAttribute('data-' + g) || '').split(/\s+/).filter(Boolean);
    });
    return { el: el, terms: terms, search: el.getAttribute('data-search') || '' };
  });

  // Parse every pill in the filter bar once up front.
  var pills = bar ? Array.prototype.slice.call(bar.querySelectorAll('.pill--filter')).map(function (el) {
    return { el: el, group: el.getAttribute('data-tax'), term: el.getAttribute('data-term'), countEl: el.querySelector('.pill__count') };
  }) : [];

  var rows = bar ? Array.prototype.slice.call(bar.querySelectorAll('.filter-bar__row')).filter(function (r) {
    return r.querySelector('.pill--filter');
  }) : [];

  // active[group] = Set of selected term slugs (OR within a group, AND across groups)
  var active = {};
  GROUPS.forEach(function (g) { active[g] = new Set(); });

  function cardMatches(card, filters, query) {
    for (var i = 0; i < GROUPS.length; i++) {
      var g = GROUPS[i];
      var wanted = filters[g];
      if (!wanted || wanted.size === 0) continue;
      var have = card.terms[g];
      var hit = false;
      for (var j = 0; j < have.length; j++) {
        if (wanted.has(have[j])) { hit = true; break; }
      }
      if (!hit) return false;
    }
    if (query && card.search.indexOf(query) === -1) return false;
    return true;
  }

  function render() {
    var query = (searchInput && searchInput.value || '').trim().toLowerCase();
    var anyActive = GROUPS.some(function (g) { return active[g].size > 0; });
    if (clearBtn) clearBtn.hidden = !(anyActive || query);

    // 1. Show/hide cards against the full active filter set.
    var visibleCount = 0;
    cards.forEach(function (card) {
      var visible = cardMatches(card, active, query);
      card.el.style.display = visible ? '' : 'none';
      if (visible) visibleCount++;
    });
    if (noResults) noResults.hidden = visibleCount !== 0;

    // 2. Recompute each pill's count as "how many cards would match if this
    //    pill were the only change" -- i.e. every OTHER group's active
    //    filters apply, but this pill's own group is ignored (selections
    //    within one group are OR'd, so they shouldn't shrink each other).
    //    A pill whose count comes out to zero and isn't already selected
    //    can't lead anywhere, so it's hidden rather than shown as dead.
    var trial = {};
    pills.forEach(function (pill) {
      GROUPS.forEach(function (g) { trial[g] = g === pill.group ? new Set() : active[g]; });
      var count = 0;
      for (var i = 0; i < cards.length; i++) {
        var card = cards[i];
        if (card.terms[pill.group].indexOf(pill.term) === -1) continue;
        if (cardMatches(card, trial, query)) count++;
      }
      if (pill.countEl) pill.countEl.textContent = count;
      var isActive = active[pill.group].has(pill.term);
      pill.el.hidden = count === 0 && !isActive;
    });

    // 3. Hide a whole facet row if every pill in it is hidden.
    rows.forEach(function (row) {
      var anyVisible = Array.prototype.some.call(row.querySelectorAll('.pill--filter'), function (p) { return !p.hidden; });
      row.hidden = !anyVisible;
    });
  }

  if (bar) {
    bar.addEventListener('click', function (e) {
      var pill = e.target.closest('.pill--filter');
      if (!pill || !bar.contains(pill)) return;
      e.preventDefault();
      var group = pill.getAttribute('data-tax');
      var term = pill.getAttribute('data-term');
      if (!group || !term) return;
      if (active[group].has(term)) {
        active[group].delete(term);
        pill.classList.remove('active');
      } else {
        active[group].add(term);
        pill.classList.add('active');
      }
      render();
    });
  }

  if (searchInput) {
    var debounceTimer;
    searchInput.addEventListener('input', function () {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(render, 80);
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      GROUPS.forEach(function (g) { active[g].clear(); });
      if (searchInput) searchInput.value = '';
      pills.forEach(function (p) { p.el.classList.remove('active'); });
      render();
    });
  }

  render();
})();
