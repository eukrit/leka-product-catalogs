/**
 * Vinci Play Product Catalog — Frontend App
 * Leka Design System
 */
(function () {
  'use strict';

  const PAGE_SIZE = 48;
  let allProducts = [];
  let filteredProducts = [];
  let seriesData = [];
  let currentPage = 0;
  let activeSeries = '';

  // DOM refs
  const grid = document.getElementById('product-grid');
  const searchInput = document.getElementById('search');
  const filterSeries = document.getElementById('filter-series');
  const filterCategory = document.getElementById('filter-category');
  const filterAge = document.getElementById('filter-age');
  const btnReset = document.getElementById('btn-reset');
  const btnLoadMore = document.getElementById('btn-load-more');
  const loadMoreWrap = document.getElementById('load-more');
  const seriesBadges = document.getElementById('series-badges');
  const modalOverlay = document.getElementById('modal-overlay');
  const modalBody = document.getElementById('modal-body');
  const modalClose = document.getElementById('modal-close');

  // Badge color rotation
  const badgeColors = ['badge-purple', 'badge-navy', 'badge-amber', 'badge-magenta', 'badge-red-orange'];

  async function loadData() {
    try {
      const [productsRes, seriesRes] = await Promise.all([
        fetch('data/products_all.json'),
        fetch('data/series.json'),
      ]);
      allProducts = await productsRes.json();
      seriesData = await seriesRes.json();

      // Update stats
      document.getElementById('stat-products').textContent = allProducts.length.toLocaleString();
      document.getElementById('stat-series').textContent = seriesData.filter(s => s.product_count > 0).length;

      populateFilters();
      renderSeriesBadges();
      applyFilters();
    } catch (err) {
      grid.innerHTML = '<div class="no-results"><h3>Failed to load data</h3><p>' + err.message + '</p></div>';
    }
  }

  function populateFilters() {
    // Series dropdown
    const seriesWithProducts = seriesData.filter(s => s.product_count > 0).sort((a, b) => a.name.localeCompare(b.name));
    seriesWithProducts.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.slug;
      opt.textContent = s.name + ' (' + s.product_count + ')';
      filterSeries.appendChild(opt);
    });

    // Category dropdown
    const categories = [...new Set(allProducts.map(p => p.category))].filter(Boolean).sort();
    categories.forEach(cat => {
      const opt = document.createElement('option');
      opt.value = cat;
      opt.textContent = cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      filterCategory.appendChild(opt);
    });
  }

  function renderSeriesBadges() {
    seriesBadges.innerHTML = '';
    const seriesWithProducts = seriesData.filter(s => s.product_count > 0).sort((a, b) => b.product_count - a.product_count);

    // "All" badge
    const allBadge = document.createElement('button');
    allBadge.className = 'badge ' + (activeSeries === '' ? 'badge-purple' : 'badge-outline');
    allBadge.innerHTML = 'All <span class="badge-count">' + allProducts.length + '</span>';
    allBadge.onclick = () => { activeSeries = ''; filterSeries.value = ''; applyFilters(); renderSeriesBadges(); };
    seriesBadges.appendChild(allBadge);

    seriesWithProducts.forEach((s, i) => {
      const badge = document.createElement('button');
      const colorClass = activeSeries === s.slug ? badgeColors[i % badgeColors.length] : 'badge-outline';
      badge.className = 'badge ' + colorClass;
      badge.innerHTML = s.name + ' <span class="badge-count">' + s.product_count + '</span>';
      badge.onclick = () => {
        activeSeries = activeSeries === s.slug ? '' : s.slug;
        filterSeries.value = activeSeries;
        applyFilters();
        renderSeriesBadges();
      };
      seriesBadges.appendChild(badge);
    });
  }

  function applyFilters() {
    const query = searchInput.value.toLowerCase().trim();
    const series = filterSeries.value || activeSeries;
    const category = filterCategory.value;
    const age = filterAge.value;

    filteredProducts = allProducts.filter(p => {
      if (query) {
        const searchable = [p.name, p.item_code, p.description, p.series_name].join(' ').toLowerCase();
        if (!searchable.includes(query)) return false;
      }
      if (series && p.series_slug !== series) return false;
      if (category && p.category !== category) return false;
      if (age) {
        const ageGroup = (p.specifications && p.specifications.age_group) || '';
        if (!ageGroup.includes(age.replace('+', ''))) return false;
      }
      return true;
    });

    currentPage = 0;
    renderProducts();
  }

  function renderProducts() {
    const start = 0;
    const end = (currentPage + 1) * PAGE_SIZE;
    const visible = filteredProducts.slice(start, end);

    if (visible.length === 0) {
      grid.innerHTML = '<div class="no-results"><h3>No products found</h3><p>Try adjusting your filters or search query.</p></div>';
      loadMoreWrap.style.display = 'none';
      return;
    }

    grid.innerHTML = visible.map(productCard).join('');
    loadMoreWrap.style.display = end < filteredProducts.length ? 'block' : 'none';

    // Attach click handlers
    grid.querySelectorAll('.product-card').forEach(card => {
      card.addEventListener('click', () => {
        const idx = parseInt(card.dataset.index);
        openModal(filteredProducts[idx]);
      });
    });
  }

  function productCard(product, index) {
    const img = product.images && product.images.length > 0
      ? product.images.find(i => i.is_primary) || product.images[0]
      : null;
    const specs = product.specifications || {};
    const dims = product.dimensions || {};

    const dimStr = dims.length_cm && dims.width_cm
      ? dims.length_cm + ' × ' + dims.width_cm + (dims.height_cm ? ' × ' + dims.height_cm : '') + ' cm'
      : '';

    const downloadCount = (product.downloads || []).length;
    const isNew = (product.tags || []).includes('new');

    return '<div class="product-card" data-index="' + index + '">' +
      '<div class="card-image">' +
        (img ? '<img src="' + img.url + '" alt="' + escapeHtml(product.name) + '" loading="lazy">' : '<div class="card-image-placeholder">🎪</div>') +
        '<span class="card-series-badge">' + escapeHtml(product.series_name || '') + '</span>' +
        (isNew ? '<span class="card-new-badge">NEW</span>' : '') +
      '</div>' +
      '<div class="card-body">' +
        '<div class="card-code">' + escapeHtml(product.item_code || '') + '</div>' +
        '<div class="card-title">' + escapeHtml(product.name || '') + '</div>' +
        '<div class="card-specs">' +
          (specs.age_group ? '<span class="spec-tag">' + escapeHtml(specs.age_group) + '</span>' : '') +
          (specs.num_users ? '<span class="spec-tag">' + escapeHtml(String(specs.num_users)) + '</span>' : '') +
          (specs.safety_zone_m2 ? '<span class="spec-tag">SZ: ' + escapeHtml(String(specs.safety_zone_m2)) + '</span>' : '') +
        '</div>' +
      '</div>' +
      '<div class="card-footer">' +
        '<div class="card-dims">' + escapeHtml(dimStr) + '</div>' +
        '<div class="card-downloads">' +
          (downloadCount > 0 ? '<span class="download-icon" title="' + downloadCount + ' downloads">📥</span>' : '') +
        '</div>' +
      '</div>' +
    '</div>';
  }

  function openModal(product) {
    const specs = product.specifications || {};
    const dims = product.dimensions || {};
    const images = product.images || [];
    const downloads = product.downloads || [];
    const certs = product.certifications || [];

    // Render images (show renders only, max 6)
    const renderImages = images.filter(i => i.view_type === 'render' || i.view_type === 'top' || i.view_type === 'front').slice(0, 6);

    let html = '';

    // Images carousel
    if (renderImages.length > 0) {
      html += '<div class="modal-images">';
      renderImages.forEach(img => {
        html += '<img src="' + img.url + '" alt="' + escapeHtml(img.view_type) + '" loading="lazy">';
      });
      html += '</div>';
    }

    html += '<div class="modal-content">';
    html += '<div class="modal-title">' + escapeHtml(product.name || '') + '</div>';
    html += '<div class="modal-code">' + escapeHtml(product.series_name + ' · ' + product.item_code) + '</div>';

    // Specifications
    const specEntries = [
      ['Length', dims.length_cm ? dims.length_cm + ' cm' : null],
      ['Width', dims.width_cm ? dims.width_cm + ' cm' : null],
      ['Height', dims.height_cm ? dims.height_cm + ' cm' : null],
      ['Age Group', specs.age_group],
      ['Users', specs.num_users],
      ['Safety Zone', specs.safety_zone_m2 ? specs.safety_zone_m2 + ' m²' : null],
      ['Free Fall Height', specs.free_fall_height_cm ? specs.free_fall_height_cm + ' cm' : null],
      ['EN Standard', specs.en_standard],
      ['Spare Parts', specs.spare_parts_available],
    ].filter(([, v]) => v != null);

    if (specEntries.length > 0) {
      html += '<div class="modal-section"><h3>Specifications</h3><div class="specs-grid">';
      specEntries.forEach(([label, value]) => {
        html += '<div class="spec-item"><div class="spec-item-label">' + escapeHtml(label) + '</div><div class="spec-item-value">' + escapeHtml(String(value)) + '</div></div>';
      });
      html += '</div></div>';
    }

    // Downloads
    if (downloads.length > 0) {
      html += '<div class="modal-section"><h3>Downloads</h3><div class="modal-downloads">';
      downloads.forEach(dl => {
        html += '<a href="' + dl.url + '" target="_blank" rel="noopener" class="modal-download-btn" onclick="event.stopPropagation()">' +
          (dl.format === 'dwg' ? '📐' : '📄') + ' ' + escapeHtml(dl.label) +
        '</a>';
      });
      html += '</div></div>';
    }

    // Certifications
    if (certs.length > 0) {
      html += '<div class="modal-section"><h3>Certifications</h3><div class="modal-certs">';
      certs.forEach(cert => {
        html += '<span class="cert-badge">' + escapeHtml(cert) + '</span>';
      });
      html += '</div></div>';
    }

    // View on website link
    if (product.source_url || product.url) {
      html += '<div class="modal-section">';
      html += '<a href="' + (product.source_url || product.url) + '" target="_blank" rel="noopener" class="modal-link" onclick="event.stopPropagation()">View on vinci-play.com →</a>';
      html += '</div>';
    }

    html += '</div>';

    modalBody.innerHTML = html;
    modalOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    modalOverlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // Event listeners
  searchInput.addEventListener('input', debounce(applyFilters, 300));
  filterSeries.addEventListener('change', () => { activeSeries = filterSeries.value; applyFilters(); renderSeriesBadges(); });
  filterCategory.addEventListener('change', applyFilters);
  filterAge.addEventListener('change', applyFilters);
  btnReset.addEventListener('click', () => {
    searchInput.value = '';
    filterSeries.value = '';
    filterCategory.value = '';
    filterAge.value = '';
    activeSeries = '';
    applyFilters();
    renderSeriesBadges();
  });
  btnLoadMore.addEventListener('click', () => { currentPage++; renderProducts(); });
  modalClose.addEventListener('click', closeModal);
  modalOverlay.addEventListener('click', (e) => { if (e.target === modalOverlay) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

  function debounce(fn, ms) {
    let timer;
    return function () {
      clearTimeout(timer);
      timer = setTimeout(fn, ms);
    };
  }

  // Init
  loadData();
})();
