/**
 * Vortex Aquatics Product Catalog — Frontend
 * Uses Vortex Design System tokens (see ../DESIGN_SYSTEM.md)
 */
(function () {
  'use strict';

  const TYPE_LABELS = {
    'splashpad': 'Splashpad',
    'waterslide': 'Waterslide',
    'elevations-playnuk': 'Elevations & PlayNuk',
    'playable-fountains': 'Playable Fountains',
    'coolhub': 'CoolHub',
    'dream-tunnel': 'Dream Tunnel',
    'water-management-solutions': 'Water Management',
    'uncategorized': 'Other',
  };

  let allProducts = [];
  let families = [];
  let activeType = '';
  let searchQuery = '';

  const grid = document.getElementById('product-grid');
  const searchInput = document.getElementById('search');
  const filterType = document.getElementById('filter-type');
  const btnReset = document.getElementById('btn-reset');
  const typeChips = document.getElementById('type-chips');
  const modalOverlay = document.getElementById('modal-overlay');
  const modalBody = document.getElementById('modal-body');
  const modalClose = document.getElementById('modal-close');

  async function loadData() {
    try {
      const [productsRes, familiesRes] = await Promise.all([
        fetch('data/products_all.json'),
        fetch('data/families.json').catch(() => null),
      ]);
      allProducts = await productsRes.json();
      families = familiesRes ? await familiesRes.json() : [];

      document.getElementById('stat-products').textContent = allProducts.length.toLocaleString();
      const typesSet = new Set();
      allProducts.forEach(p => (p.product_types || []).forEach(t => typesSet.add(t)));
      document.getElementById('stat-types').textContent = typesSet.size || '—';

      populateFilters(typesSet);
      renderChips(typesSet);
      render();
    } catch (err) {
      grid.innerHTML = '<div class="no-results"><h3>Failed to load catalog</h3><p>' + err.message + '</p></div>';
      console.error(err);
    }
  }

  function populateFilters(typesSet) {
    const sortedTypes = [...typesSet].sort();
    sortedTypes.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = TYPE_LABELS[t] || t;
      filterType.appendChild(opt);
    });
  }

  function renderChips(typesSet) {
    typeChips.innerHTML = '';
    const counts = {};
    allProducts.forEach(p => {
      const types = (p.product_types && p.product_types.length) ? p.product_types : ['uncategorized'];
      types.forEach(t => { counts[t] = (counts[t] || 0) + 1; });
    });

    const mkChip = (value, label, count) => {
      const btn = document.createElement('button');
      btn.className = 'chip' + (activeType === value ? ' active' : '');
      btn.innerHTML = label + '<span class="chip-count">' + count + '</span>';
      btn.onclick = () => { activeType = (activeType === value) ? '' : value; filterType.value = activeType; render(); renderChips(typesSet); };
      return btn;
    };

    typeChips.appendChild(mkChip('', 'All', allProducts.length));
    Object.keys(counts)
      .sort((a, b) => counts[b] - counts[a])
      .forEach(t => typeChips.appendChild(mkChip(t, TYPE_LABELS[t] || t, counts[t])));
  }

  function filtered() {
    return allProducts.filter(p => {
      if (activeType) {
        const types = p.product_types || [];
        if (!types.includes(activeType) && !(activeType === 'uncategorized' && types.length === 0)) return false;
      }
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const hay = [p.name, p.model_code, p.description, p.slug].filter(Boolean).join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function render() {
    const items = filtered();
    if (items.length === 0) {
      grid.innerHTML = '<div class="no-results"><h3>No products match</h3><p>Try adjusting your filters.</p></div>';
      return;
    }
    grid.innerHTML = '';
    items.forEach(p => grid.appendChild(card(p)));
  }

  function primaryImage(p) {
    const imgs = p.images || [];
    for (const img of imgs) {
      if (img.gcs_url) return img.gcs_url;
      if (img.url) return img.url;
    }
    return '';
  }

  function card(p) {
    const el = document.createElement('article');
    el.className = 'card';
    el.onclick = () => openModal(p);
    const img = primaryImage(p);
    const types = (p.product_types || []).map(t => `<span class="card-type-tag">${TYPE_LABELS[t] || t}</span>`).join('');
    el.innerHTML = `
      <div class="card-image-wrap">
        ${img ? `<img class="card-image" src="${img}" alt="${escapeHTML(p.name || '')}" loading="lazy">` : ''}
      </div>
      <div class="card-body">
        <div class="card-code">${escapeHTML(p.model_code || '—')}</div>
        <h3 class="card-title">${escapeHTML(p.name || p.slug)}</h3>
        <p class="card-desc">${escapeHTML(p.description || '')}</p>
        <div class="card-types">${types}</div>
      </div>
    `;
    return el;
  }

  function openModal(p) {
    const img = primaryImage(p);
    const specs = p.specifications || {};
    const specRows = Object.entries(specs).map(([k, v]) => `
      <div class="spec-row">
        <span class="spec-label">${escapeHTML(k.replace(/_/g, ' '))}</span>
        <span class="spec-value">${escapeHTML(String(v))}</span>
      </div>
    `).join('');

    const gallery = (p.images || []).slice(1, 9).map(i => {
      const u = i.gcs_url || i.url;
      return u ? `<img src="${u}" alt="" loading="lazy">` : '';
    }).join('');

    const types = (p.product_types || []).map(t => `<span class="card-type-tag">${TYPE_LABELS[t] || t}</span>`).join(' ');

    modalBody.innerHTML = `
      ${img ? `<img class="modal-hero" src="${img}" alt="${escapeHTML(p.name || '')}">` : ''}
      <div class="modal-content">
        <div class="modal-code">${escapeHTML(p.model_code || '—')}</div>
        <h2 class="modal-title">${escapeHTML(p.name || p.slug)}</h2>
        <div style="margin-bottom:16px">${types}</div>
        ${p.description ? `<p class="modal-desc">${escapeHTML(p.description)}</p>` : ''}
        ${specRows ? `<div class="spec-grid">${specRows}</div>` : ''}
        ${gallery ? `<div class="modal-gallery">${gallery}</div>` : ''}
        ${p.url ? `<div class="modal-source">Source: <a href="${p.url}" target="_blank" rel="noopener">${p.url}</a></div>` : ''}
      </div>
    `;
    modalOverlay.hidden = false;
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    modalOverlay.hidden = true;
    document.body.style.overflow = '';
  }

  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  // Events
  searchInput.addEventListener('input', e => { searchQuery = e.target.value.trim(); render(); });
  filterType.addEventListener('change', e => { activeType = e.target.value; render(); renderChipsSafe(); });
  btnReset.addEventListener('click', () => { searchQuery = ''; activeType = ''; searchInput.value = ''; filterType.value = ''; render(); renderChipsSafe(); });
  modalClose.addEventListener('click', closeModal);
  modalOverlay.addEventListener('click', e => { if (e.target === modalOverlay) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

  function renderChipsSafe() {
    const typesSet = new Set();
    allProducts.forEach(p => (p.product_types || []).forEach(t => typesSet.add(t)));
    renderChips(typesSet);
  }

  loadData();
})();
