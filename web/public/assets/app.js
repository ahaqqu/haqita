
      function escapeHtml(str) {
        if (str == null) return "";
        return String(str)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;")
          .replace(/'/g, "&#39;");
      }
      function escapeAttr(str) { return escapeHtml(str); }
      function escapeSelector(str) {
        if (str == null) return "";
        return String(str).replace(/[!"#$%&'()*+,.\/:;<=>?@[\]^`{|}~\\\s]/g, (c) => "\\" + c);
      }
      function safeUrl(str) {
        if (!str) return "";
        try {
          const url = new URL(str, window.location.href);
          return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
        } catch { return ""; }
      }

      let consolidatedData = null;
      let priceHistoryData = null;
      let displayHints = null;
      let currentFilter = "all";
      let currentSort = "name";
      let currentSearch = "";
      let currentPage = 1;
      const PAGE_SIZE = 20;
      let expandedKey = null;
      let isLoadingMore = false;
      let isRefreshing = false;
      let showDummy = false;

      // Parse URL for show_dummy=true
      (function () {
        const params = new URLSearchParams(window.location.search);
        showDummy = params.get("show_dummy") === "true";
        if (showDummy) {
          document.getElementById("dummy-badge").style.display = "inline";
        }
      })();

      function getDefaultDisplayHints() {
        return {
          currency: "Rp",
          stores: { lotte: "Lotte", superindo: "Superindo" },
          store_colors: { lotte: "#0057A8", superindo: "#E8211D" },
        };
      }

      function formatIDR(n) {
        if (n == null) return "-";
        return displayHints.currency + " " + n.toLocaleString("id-ID");
      }

      function getShortDateText(isoDate) {
        if (!isoDate) return "";
        const now = new Date();
        now.setHours(0, 0, 0, 0);
        const target = new Date(isoDate);
        target.setHours(0, 0, 0, 0);
        const diffTime = target - now;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        if (diffDays < 0) return "Expired";
        if (diffDays === 0) return "Today";
        if (diffDays === 1) return "1d";
        return `${diffDays}d`;
      }

      function retryFetch(url, retries = 3, delay = 1000) {
        return fetch(url).catch((err) => {
          if (retries <= 0) throw err;
          return new Promise((resolve) => setTimeout(resolve, delay)).then(() =>
            retryFetch(url, retries - 1, delay * 2),
          );
        });
      }

      async function tryLoadWithFallback(basePath, fallbackPath, filename) {
        const tryPath = (path) => retryFetch(`${path}/${filename}`);
        try {
          const resp = await tryPath(basePath);
          if (resp.ok) return { data: await resp.json(), from: basePath };
        } catch (e) { console.warn("Primary path failed:", e); }
        try {
          const resp = await tryPath(fallbackPath);
          if (resp.ok) return { data: await resp.json(), from: fallbackPath };
        } catch (e) { console.warn("Fallback path failed:", e); }
        return { data: null, from: null };
      }

      function validateData(data, type) {
        if (!data) return { valid: false, error: "No data received" };
        if (type === "consolidated") {
          if (!data.products && !data.singles)
            return {
              valid: false,
              error: "Missing products/singles in consolidated data",
            };
        }
        return { valid: true };
      }

      function renderLoading() {
        document.getElementById("loading").style.display = "block";
        document.getElementById("product-grid").style.display = "none";
        document.getElementById("error-state").style.display = "none";
        document.getElementById("empty-state").style.display = "none";
        document.getElementById("no-results").style.display = "none";
      }

      function renderError(msg) {
        document.getElementById("loading").style.display = "none";
        document.getElementById("product-grid").style.display = "none";
        document.getElementById("error-state").style.display = "block";
        document.getElementById("error-message").textContent = msg;
      }

      function renderWarning(msg) {
        const banner = document.getElementById("warning-banner");
        banner.style.display = "flex";
        document.getElementById("warning-text").textContent = msg;
      }

      function normalizeProduct(product) {
        const key = product.key || product.product_key || "";
        if (product.stores && Array.isArray(product.stores)) {
          return { ...product, product_key: key, stores: product.stores };
        }
        if (product.store) {
          return {
            ...product,
            product_key: key,
            stores: [
              {
                store: product.store,
                price: product.price,
                effective_unit_price: product.effective_unit_price,
                promo: product.promo,
                valid_until: product.valid_until,
                image_path: product.image_path,
              },
            ],
          };
        }
        return { ...product, product_key: key, stores: [] };
      }

      function isProductInStore(product, store) {
        const normalized = normalizeProduct(product);
        return normalized.stores.some((s) =>
          (s.store || "").toLowerCase().includes(store.toLowerCase()),
        );
      }

      function searchProducts(query) {
        if (!query) return true;
        const q = query.toLowerCase();
        return (product) => {
          const name = (product.name || "").toLowerCase();
          const brand = (product.brand || "").toLowerCase();
          const unit = (product.unit || "").toLowerCase();
          return name.includes(q) || brand.includes(q) || unit.includes(q);
        };
      }

      function getAllProducts() {
        if (!consolidatedData) return [];
        const products = consolidatedData.products || [];
        const singles = consolidatedData.singles || [];
        return [...products, ...singles];
      }

      function getFilteredSortedProducts() {
        let all = getAllProducts();
        if (currentFilter !== "all") {
          all = all.filter((p) => isProductInStore(p, currentFilter));
        }
        if (currentSearch) {
          const fn = searchProducts(currentSearch);
          all = all.filter(fn);
        }
        all = [...all].sort((a, b) => {
          if (currentSort === "name")
            return (a.name || "").localeCompare(b.name || "");
          if (currentSort === "cheapest")
            return (a.price_min || 0) - (b.price_min || 0);
          if (currentSort === "savings") {
            const aGap = a.price_gap || 0;
            const bGap = b.price_gap || 0;
            if (aGap === 0 && bGap === 0) return 0;
            if (aGap === 0) return 1;
            if (bGap === 0) return -1;
            return bGap - aGap;
          }
          if (currentSort === "expiry") {
            const aDate = a.valid_until || "9999-12-31";
            const bDate = b.valid_until || "9999-12-31";
            return aDate.localeCompare(bDate);
          }
          return 0;
        });
        return all;
      }

      function filterPromos(promos) {
        if (!promos || !Array.isArray(promos)) return [];
        return promos.filter((p) => p && !p.startsWith("*Harga"));
      }

      function getPromoColorClass(promo) {
        if (!promo) return "promo-green";
        const lower = promo.toLowerCase();
        if (lower.includes("diskon")) return "promo-red";
        if (lower.includes("gratis")) return "promo-green";
        if (lower.includes("dapat")) return "promo-amber";
        return "promo-green";
      }

      function buildPromoBadges(promos) {
        const filtered = filterPromos(promos);
        if (!filtered.length) return "";
        return filtered
          .map(
            (p) =>
              `<span class="promo-badge ${getPromoColorClass(p)}">${escapeHtml(p)}</span>`,
          )
          .join(" ");
      }

      function buildStoreRows(product) {
        const normalized = normalizeProduct(product);
        return normalized.stores
          .map((s) => {
            const storeKey = (s.store || "").toLowerCase().replace(/\s+/g, "");
            const color =
              (displayHints.store_colors &&
                displayHints.store_colors[storeKey]) ||
              "#c0bfb8";
            const storeName =
              (displayHints.stores && displayHints.stores[storeKey]) || s.store;
            const promoBadges = buildPromoBadges(s.promo);
            const displayPrice =
              s.effective_unit_price && s.effective_unit_price < s.price
                ? s.effective_unit_price
                : s.price;
            return `<div class="store-row">
      <span class="store-dot" style="background:${escapeHtml(color)}"></span>
      <span class="store-name">${escapeHtml(storeName)}</span>
      <span class="store-price">${escapeHtml(formatIDR(displayPrice))}</span>
      ${promoBadges}
    </div>`;
          })
          .join("");
      }

      function buildMatchedCard(product) {
        const normalized = normalizeProduct(product);
        const key = normalized.product_key || "";
        const savingsText = product.savings_pct
          ? `Save ${product.savings_pct}%`
          : "";
        const shortDate = product.valid_until
          ? getShortDateText(product.valid_until)
          : "";
        const confBadge =
          product.match_confidence != null && product.match_confidence < 0.8
            ? `<div class="low-conf-badge">Match: ${escapeHtml(Math.round(product.match_confidence * 100))}%</div>`
            : "";
        const promoBadge = savingsText
          ? `<div class="promo-top-badge promo-green">${escapeHtml(savingsText)}</div>`
          : "";
        return `<div class="product-card" data-key="${escapeAttr(key)}" role="button" tabindex="0">
    <div class="card-body">
      <div class="product-name">${escapeHtml(product.name || "Unknown")}</div>
      <div class="product-unit">${escapeHtml(product.unit || "")}</div>
      <div class="store-rows">${buildStoreRows(product)}</div>
      ${confBadge}
      ${promoBadge}
    </div>
    <div class="card-footer">
      <div class="price-tag">
        <span class="price-label">from</span>
        ${escapeHtml(formatIDR(product.price_min))}
      </div>
      ${shortDate ? `<div class="store-meta">${escapeHtml(shortDate)} left</div>` : ""}
    </div>
    <div class="detail-panel" id="detail-${escapeAttr(key)}"></div>
  </div>`;
      }

      function buildSingleCard(product) {
        const normalized = normalizeProduct(product);
        const key = normalized.product_key || "";
        const s = normalized.stores[0] || {};
        const storeKey = (s.store || "").toLowerCase().replace(/\s+/g, "");
        const color =
          (displayHints.store_colors && displayHints.store_colors[storeKey]) ||
          "var(--gray-300)";
        const storeName =
          (displayHints.stores && displayHints.stores[storeKey]) || s.store;
        const shortDate = product.valid_until
          ? getShortDateText(product.valid_until)
          : "";
        const confBadge =
          product.match_confidence != null && product.match_confidence < 0.8
            ? `<div class="low-conf-badge">Match: ${escapeHtml(Math.round(product.match_confidence * 100))}%</div>`
            : "";
        const displayPrice =
          s.effective_unit_price && s.effective_unit_price < s.price
            ? s.effective_unit_price
            : s.price;
        const hasPromo =
          s.effective_unit_price && s.effective_unit_price < s.price;
        const promoBadgesSingle = hasPromo ? buildPromoBadges(s.promo) : "";
        return `<div class="product-card" data-key="${escapeAttr(key)}" role="button" tabindex="0">
    <div class="card-body">
      <div class="product-name">${escapeHtml(product.name || "Unknown")}</div>
      <div class="product-unit">${escapeHtml(product.unit || "")}</div>
      ${confBadge}
      ${promoBadgesSingle}
    </div>
    <div class="card-footer">
      <div class="price-tag">
        <span class="price-label">price</span>
        ${escapeHtml(formatIDR(displayPrice))}
      </div>
      <div class="store-meta">
        <span class="store-dot" style="background:${escapeHtml(color)}"></span>
        ${escapeHtml(storeName)}${shortDate ? ` · ${escapeHtml(shortDate)}` : ""}
      </div>
    </div>
    <div class="detail-panel" id="detail-${escapeAttr(key)}"></div>
  </div>`;
      }

      function buildDetailPanel(product) {
        const normalized = normalizeProduct(product);
        const key = normalized.product_key || "";
        const cheapestStore = (product.cheapest_store || "")
          .toLowerCase()
          .replace(/\s+/g, "");
        let storeRows = normalized.stores
          .map((s) => {
            const storeKey = (s.store || "").toLowerCase().replace(/\s+/g, "");
            const isCheapest = storeKey === cheapestStore;
            const color =
              (displayHints.store_colors &&
                displayHints.store_colors[storeKey]) ||
              "var(--gray-300)";
            const storeName =
              (displayHints.stores && displayHints.stores[storeKey]) || s.store;
            const hasPromo =
              s.effective_unit_price && s.effective_unit_price < s.price;
            const displayPrice = hasPromo ? s.effective_unit_price : s.price;
            const originalPrice = hasPromo
              ? `<span class="original-price">${escapeHtml(formatIDR(s.price))}</span> `
              : "";
            const unitPrice =
              s.effective_unit_price && s.effective_unit_price !== displayPrice
                ? ` · ${escapeHtml(formatIDR(s.effective_unit_price))}/pc`
                : "";
            const brochureLink = s.image_path
              ? `<a class="brochure-link" href="${escapeAttr(safeUrl(s.image_path))}" target="_blank" rel="noopener noreferrer">View Brochure</a>`
              : "";
            const diff =
              product.price_gap && !isCheapest
                ? ` +${escapeHtml(formatIDR(product.price_gap))}`
                : "";
            const cheapestBadge = isCheapest ? ` ✓ Cheapest` : "";
            return `<div class="detail-store-row ${isCheapest ? "cheapest" : ""}">
      <span class="store-dot" style="background:${escapeHtml(color)}"></span>
      <span class="store-name">${escapeHtml(storeName)}${cheapestBadge}</span>
      <span class="store-price">${originalPrice}${escapeHtml(formatIDR(displayPrice))}${unitPrice}${diff}</span>
      ${brochureLink}
    </div>`;
          })
          .join("");

        const confText =
          product.match_confidence != null
            ? `Match confidence: ${Math.round(product.match_confidence * 100)}% (${escapeHtml(product.match_method || "unknown")})`
            : "";

        return `<div class="detail-section">
    <h4>Price Comparison</h4>
    ${storeRows}
  </div>
  <div class="detail-section">
    <h4>Price Trend</h4>
    <div class="chart-container">
      <canvas id="chart-${escapeAttr(key)}" role="img" aria-label="${escapeAttr("Price trend chart for " + (product.name || "Unknown product"))}"></canvas>
    </div>
  </div>
  ${confText ? `<div class="detail-section"><p style="font-size:0.82rem;color:var(--gray-700)">${escapeHtml(confText)}</p></div>` : ""}`;
      }

      function drawBarChart(canvas, productKey, history) {
        if (!canvas || !history || !history.snapshots) return;
        const snapshots = history.snapshots
          .filter((s) => s.product_key === productKey)
          .sort((a, b) => (a.date || "").localeCompare(b.date || ""));
        if (snapshots.length < 2) {
          canvas.parentElement.innerHTML =
            '<div class="no-history">No history available</div>';
          return;
        }
        const parent = canvas.parentElement;
        if (!parent._chartResizeObserver) {
          parent._chartResizeObserver = new ResizeObserver(
            debounce(() => drawBarChart(canvas, productKey, history), 150),
          );
          parent._chartResizeObserver.observe(parent);
        }
        const ctx = canvas.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        const rect = parent.getBoundingClientRect();
        canvas.width = rect.width * dpr;
        canvas.height = rect.height * dpr;
        ctx.scale(dpr, dpr);
        const w = rect.width;
        const h = rect.height;
        const padding = { top: 10, right: 10, bottom: 25, left: 10 };
        const chartW = w - padding.left - padding.right;
        const chartH = h - padding.top - padding.bottom;
        const prices = snapshots.map((s) => {
          const effective =
            s.effective_unit_price && s.effective_unit_price < s.price
              ? s.effective_unit_price
              : s.price;
          return effective || 0;
        });
        const maxPrice = Math.max(...prices);
        const barWidth = Math.min(30, (chartW / snapshots.length) * 0.6);
        const gap =
          (chartW - barWidth * snapshots.length) / (snapshots.length + 1);
        snapshots.forEach((s, i) => {
          const effective =
            s.effective_unit_price && s.effective_unit_price < s.price
              ? s.effective_unit_price
              : s.price;
          const barH = (effective / maxPrice) * chartH;
          const x = padding.left + gap + i * (barWidth + gap);
          const y = padding.top + chartH - barH;
          ctx.fillStyle = "#4a9e6a";
          ctx.fillRect(x, y, barWidth, barH);
          ctx.fillStyle = "#8a8880";
          ctx.font = "10px 'Plus Jakarta Sans', sans-serif";
          ctx.textAlign = "center";
          const d = new Date(s.date);
          ctx.fillText(
            d.getDate() + "/" + (d.getMonth() + 1),
            x + barWidth / 2,
            h - 5,
          );
        });
      }

      function debounce(fn, ms) {
        let timer;
        return function (...args) {
          clearTimeout(timer);
          timer = setTimeout(() => fn.apply(this, args), ms);
        };
      }

      function validatePriceHistoryKey(productKey) {
        if (!priceHistoryData || !priceHistoryData.snapshots) return false;
        return priceHistoryData.snapshots.some(
          (s) => s.product_key === productKey,
        );
      }

      function expandCard(key) {
        const escapedKey = escapeSelector(key);
        const card = document.querySelector(`.product-card[data-key="${escapedKey}"]`);
        if (!card) return;
        if (expandedKey && expandedKey !== key) {
          const prevEscaped = escapeSelector(expandedKey);
          const prev = document.querySelector(
            `.product-card[data-key="${prevEscaped}"]`,
          );
          if (prev) {
            prev.classList.remove("expanded");
            const prevDetail = document.getElementById(`detail-${expandedKey}`);
            if (prevDetail) prevDetail.innerHTML = "";
          }
        }
        const isExpanded = card.classList.contains("expanded");
        if (isExpanded) {
          card.classList.remove("expanded");
          const detail = document.getElementById(`detail-${key}`);
          if (detail) detail.innerHTML = "";
          expandedKey = null;
          history.replaceState(null, "", window.location.pathname);
        } else {
          card.classList.add("expanded");
          const allProducts = getAllProducts();
          const product = allProducts.find(
            (p) => (p.key || p.product_key) === key,
          );
          if (product) {
            const detail = document.getElementById(`detail-${key}`);
            if (detail) {
              detail.innerHTML = buildDetailPanel(product);
              setTimeout(() => {
                const canvas = document.getElementById(`chart-${key}`);
                if (canvas && validatePriceHistoryKey(key)) {
                  drawBarChart(canvas, key, priceHistoryData);
                } else if (canvas) {
                  canvas.parentElement.innerHTML =
                    '<div class="no-history">No history available</div>';
                }
              }, 50);
            }
          }
          expandedKey = key;
          history.replaceState(null, "", "#" + key);
        }
      }

      function renderCards() {
        const grid = document.getElementById("product-grid");
        const filtered = getFilteredSortedProducts();

        if (filtered.length === 0 && getAllProducts().length === 0) {
          document.getElementById("loading").style.display = "none";
          document.getElementById("empty-state").style.display = "block";
          document.getElementById("product-grid").style.display = "none";
          document.getElementById("no-results").style.display = "none";
          document.getElementById("load-more-sentinel").style.display = "none";
          return;
        }

        if (filtered.length === 0 && currentSearch) {
          document.getElementById("loading").style.display = "none";
          document.getElementById("no-results").style.display = "block";
          document.getElementById("no-results-query").textContent =
            currentSearch;
          document.getElementById("product-grid").style.display = "none";
          document.getElementById("load-more-sentinel").style.display = "none";
          return;
        }

        document.getElementById("loading").style.display = "none";
        document.getElementById("empty-state").style.display = "none";
        document.getElementById("no-results").style.display = "none";
        document.getElementById("product-grid").style.display = "grid";

        const end = currentPage * PAGE_SIZE;
        const pageItems = filtered.slice(0, end);

        // Only rebuild grid if filter/search changed (page === 1), otherwise append
        // Also rebuild on auto-refresh to prevent stale cards
        const shouldRebuild = currentPage === 1 || isRefreshing;

        if (shouldRebuild) {
          grid.innerHTML = "";
        }

        // Render only the new slice for this page
        const startIdx = (currentPage - 1) * PAGE_SIZE;
        const newItems = pageItems.slice(startIdx);

        const html = newItems
          .map((p) => {
            const normalized = normalizeProduct(p);
            return normalized.stores.length > 1
              ? buildMatchedCard(p)
              : buildSingleCard(p);
          })
          .join("");

        // Append new items
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = html;
        while (tempDiv.firstChild) {
          const card = tempDiv.firstChild;
          grid.appendChild(card);
          // Attach event listeners to new cards
          if (card.classList && card.classList.contains("product-card")) {
            card.addEventListener("click", () => expandCard(card.dataset.key));
            card.addEventListener("keydown", (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                expandCard(card.dataset.key);
              }
            });
          }
        }

        // Manage sentinel visibility
        const sentinel = document.getElementById("load-more-sentinel");
        if (end < filtered.length) {
          sentinel.style.display = "block";
        } else {
          sentinel.style.display = "none";
        }

        renderFooterStats(filtered);
      }
      function renderFooterStats(filtered) {
        const stats = consolidatedData.stats || {};
        const lotteCount = filtered.filter((p) =>
          isProductInStore(p, "lotte"),
        ).length;
        const superindoCount = filtered.filter((p) =>
          isProductInStore(p, "superindo"),
        ).length;
        const matchedCount = filtered.filter((p) => {
          const n = normalizeProduct(p);
          return n.stores.length > 1;
        }).length;
        document.getElementById("footer-stats").textContent =
          `Lotte: ${lotteCount} products · Superindo: ${superindoCount} · Matched: ${matchedCount}`;
        const reviewEl = document.getElementById("footer-review");
        if (stats.flagged_for_review > 0) {
          reviewEl.innerHTML = `<a href="admin.html" style="color:var(--amber);text-decoration:none">⚠ ${escapeHtml(stats.flagged_for_review)} items need review →</a>`;
          reviewEl.className = "review-warning";
        } else {
          reviewEl.textContent = "";
        }
      }

      function updateFreshnessBar(timestamp) {
        if (!timestamp) {
          document.getElementById("freshness-text").textContent = "Loading...";
          return;
        }
        const now = new Date();
        const updated = new Date(timestamp);
        const diffMs = now - updated;
        const diffMin = Math.floor(diffMs / 60000);
        const diffHr = Math.floor(diffMin / 60);
        let text = "";
        if (diffMin < 1) text = "Just now";
        else if (diffMin < 60) text = `${diffMin}m ago`;
        else text = `${diffHr}h ${diffMin % 60}m ago`;
        document.getElementById("freshness-text").textContent =
          `Prices updated ${text}`;
      }

      function setupHashRouting() {
        window.addEventListener("hashchange", () => {
          const key = window.location.hash.slice(1);
          if (key) expandCard(key);
        });
      }

      function applyHashAfterLoad() {
        const key = window.location.hash.slice(1);
        if (key) {
          setTimeout(() => expandCard(key), 100);
        }
      }

      function startAutoRefresh(intervalMs = 300000) {
        setInterval(() => {
          if (document.visibilityState === "visible") {
            loadData(true);
          }
        }, intervalMs);
      }

      // API-first loading helpers
      const API_BASE = "/api/v1";

      async function loadFromAPI(endpoint, forceShowDummy) {
        try {
          const suffix =
            (forceShowDummy !== undefined ? forceShowDummy : showDummy) &&
            !endpoint.includes("show_dummy")
              ? endpoint.includes("?")
                ? "&show_dummy=true"
                : "?show_dummy=true"
              : "";
          const resp = await retryFetch(`${API_BASE}${endpoint}${suffix}`);
          if (!resp.ok) return null;
          return await resp.json();
        } catch (e) {
          console.warn(`API ${endpoint} failed, falling back to static JSON`);
          return null;
        }
      }

      function setDataSource(source) {
        const el = document.getElementById("data-source");
        if (el) el.textContent = `(${source === "api" ? "API" : "static"})`;
      }

      async function loadData(isRefresh = false) {
        if (!isRefresh) renderLoading();
        document.getElementById("warning-banner").style.display = "none";
        document.getElementById("sample-banner").style.display = "none";
        try {
          const STATIC_PATH = "output/html";
          const SAMPLE_PATH = "data/sample/html";

          // API-first: try the API for consolidated product data
          let consSource = "api";
          let consOk = false;
          const apiProducts = await loadFromAPI("/products?limit=100");
          if (apiProducts && apiProducts.data) {
            const products = apiProducts.data;
            // Fetch store colors from the API
            const storesResp = await loadFromAPI("/stores");
            const storeColors = {};
            if (storesResp && storesResp.data) {
              for (const s of storesResp.data) {
                if (s.color) storeColors[s.name] = s.color;
              }
            }
            consolidatedData = {
              products: products.filter((p) => p.stores && p.stores.length > 1),
              singles: products.filter(
                (p) => !p.stores || p.stores.length <= 1,
              ),
              stats: {},
              display_hints: {
                stores: {},
                store_colors: storeColors,
                currency: "IDR",
              },
              generated_at: new Date().toISOString(),
            };
            consOk = true;
          }

          // Fallback to static JSON if API failed
          if (!consOk) {
            consSource = "static";
            const consLoad = await tryLoadWithFallback(
              STATIC_PATH,
              SAMPLE_PATH,
              "active_promo.json",
            );
            if (consLoad.data) {
              const v = validateData(consLoad.data, "consolidated");
              if (v.valid) {
                consolidatedData = consLoad.data;
                consOk = true;
              } else {
                renderError(v.error);
                return;
              }
            }
          }

          // API-first: try the API for price history
          let histSource = "api";
          let histOk = false;
          const apiPrices = await loadFromAPI("/prices?limit=100");
          if (apiPrices && apiPrices.data) {
            priceHistoryData = { snapshots: apiPrices.data };
            histOk = true;
          }

          // Fallback to static JSON if API failed
          if (!histOk) {
            histSource = "static";
            const histLoad = await tryLoadWithFallback(
              STATIC_PATH,
              SAMPLE_PATH,
              "price_history.json",
            );
            if (histLoad.data) {
              priceHistoryData = histLoad.data;
              histOk = true;
            }
          }

          // Set data source indicator (prefer API)
          setDataSource(consSource === "api" ? "api" : "static");

          if (!consOk && !histOk) {
            renderError(
              "Could not fetch any product data. Make sure the pipeline has run and an HTTP server is serving the files (e.g., python -m http.server 8080 --directory web/public).",
            );
            return;
          }
          if (!consOk && histOk) {
            renderWarning(
              "Consolidated data unavailable. Showing price history only.",
            );
            consolidatedData = {
              products: [],
              singles: [],
              display_hints: getDefaultDisplayHints(),
              stats: {},
            };
          }
          if (!histOk && consOk) {
            if (!isRefresh)
              renderWarning(
                "Price history unavailable. Charts will not display.",
              );
            priceHistoryData = null;
          }
          const isSample =
            consolidatedData?.is_sample === true ||
            priceHistoryData?.is_sample === true;
          if (isSample) {
            const banner = document.getElementById("sample-banner");
            banner.style.display = "flex";
            banner.innerHTML =
              'Displaying sample data. <a href="#" id="sample-reload" style="color:var(--amber);margin-left:0.5rem">Refresh to try real data</a>';
          }
          displayHints =
            consolidatedData?.display_hints || getDefaultDisplayHints();
          if (displayHints.store_colors) {
            const normalizedColors = {};
            for (const [key, value] of Object.entries(
              displayHints.store_colors,
            )) {
              normalizedColors[key.toLowerCase().replace(/\s+/g, "")] = value;
            }
            displayHints.store_colors = normalizedColors;
          }
          if (displayHints.stores) {
            const normalizedStores = {};
            for (const [key, value] of Object.entries(displayHints.stores)) {
              normalizedStores[key.toLowerCase().replace(/\s+/g, "")] = value;
            }
            displayHints.stores = normalizedStores;
          }
          if (consolidatedData?.generated_at) {
            updateFreshnessBar(consolidatedData.generated_at);
          }
          if (isRefresh) isRefreshing = true;
          try {
            renderCards();
          } finally {
            isRefreshing = false;
          }
          if (document.getElementById("view-promos")?.classList.contains("active")) renderPromos();
          if (document.getElementById("view-brochures")?.classList.contains("active")) renderBrochures();
          if (!isRefresh) {
            setupHashRouting();
            setTimeout(() => applyHashAfterLoad(), 150);
          }
        } catch (err) {
          renderError("Network error: " + err.message);
        }
      }

      document.getElementById("search-input").addEventListener("input", (e) => {
        clearTimeout(window._searchTimeout);
        window._searchTimeout = setTimeout(() => {
          currentSearch = e.target.value.trim();
          currentPage = 1;
          renderCards();
        }, 200);
      });

      document.querySelectorAll(".chip").forEach((chip) => {
        chip.addEventListener("click", () => {
          document
            .querySelectorAll(".chip")
            .forEach((c) => {
              c.classList.remove("active");
              c.setAttribute("aria-pressed", "false");
            });
          chip.classList.add("active");
          chip.setAttribute("aria-pressed", "true");
          currentFilter = chip.dataset.filter;
          currentPage = 1;
          renderCards();
        });
      });

      document.getElementById("sort-select").addEventListener("change", (e) => {
        currentSort = e.target.value;
        currentPage = 1;
        renderCards();
      });

      const loadMoreObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting && !isLoadingMore) {
              const filtered = getFilteredSortedProducts();
              const end = currentPage * PAGE_SIZE;
              if (end < filtered.length) {
                isLoadingMore = true;
                currentPage++;
                renderCards();
                // Re-enable observer after a short delay to let layout settle
                setTimeout(() => {
                  isLoadingMore = false;
                }, 100);
              }
            }
          });
        },
        { rootMargin: "200px" },
      );

      loadMoreObserver.observe(document.getElementById("load-more-sentinel"));

      document.getElementById("warning-retry").addEventListener("click", () => {
        loadData();
      });

      document.getElementById("retry-btn").addEventListener("click", () => {
        loadData();
      });

      document.getElementById("sample-banner").addEventListener("click", (e) => {
        if (e.target.id === "sample-reload") {
          e.preventDefault();
          location.reload();
        }
      });

      function renderPromos() {
        const el = document.getElementById("promos-content");
        if (!el || !consolidatedData) return;
        const catalog = consolidatedData.promo_catalog;
        if (!catalog || !catalog.length) {
          el.innerHTML =
            '<div class="empty-box"><h3>No promos available</h3><p>Promo data will appear here after the next pipeline run.</p></div>';
          return;
        }
        const typeLabels = {
          discount_pct: "Discount %",
          discount_fixed: "Discount (Fixed)",
          bogo: "Buy One Get One",
          bundle: "Bundle",
          member_price: "Member Price",
          promo_price: "Promo Price",
          freebie: "Freebie",
          quantity_limit: "Quantity Limit",
          special: "Other",
        };
        const groups = {};
        catalog.forEach((p) => {
          const label = typeLabels[p.type] || "Other";
          if (!groups[label]) groups[label] = [];
          groups[label].push(p);
        });
        let html = '<div class="filter-chips" style="margin-bottom:1rem">';
        html +=
          '<button class="chip active" data-promo-filter="all" aria-pressed="true">All</button>';
        html += '<button class="chip" data-promo-filter="lotte" aria-pressed="false">Lotte</button>';
        html +=
          '<button class="chip" data-promo-filter="superindo" aria-pressed="false">Superindo</button>';
        html += "</div>";
        const order = [
          "Discount %",
          "Discount (Fixed)",
          "Buy One Get One",
          "Bundle",
          "Member Price",
          "Promo Price",
          "Freebie",
          "Quantity Limit",
          "Other",
        ];
        order.forEach((label) => {
          if (!groups[label]) return;
          html +=
            '<div class="promo-type-group"><h3 class="promo-type-header">' +
            label +
            "</h3>";
          groups[label].forEach((p) => {
            const storeHtml = Object.entries(p.stores || {})
              .map(
                ([s, c]) =>
                  '<span class="promo-store-badge" style="background:' +
                  (s === "Lotte" ? "var(--lotte)" : "var(--superindo)") +
                  ';color:white;padding:2px 6px;border-radius:4px;font-size:0.75rem">' +
                  escapeHtml(s) +
                  " " +
                  escapeHtml(c) +
                  "</span>",
              )
              .join(" ");
            html += '<div class="promo-card" data-promo-key="' + escapeAttr(p.key) + '">';
            html +=
              '<div class="promo-card-header"><strong>' +
              escapeHtml(p.display) +
              '</strong> <span class="promo-count-badge">' +
              escapeHtml(p.product_count) +
              " products</span></div>";
            html += '<div class="promo-card-meta">' + storeHtml + "</div>";
            if (p.example_products && p.example_products.length) {
              html +=
                '<div class="promo-card-products" style="display:none;margin-top:0.5rem;padding-top:0.5rem;border-top:1px solid var(--gray-100)">';
              p.example_products.forEach((name) => {
                html +=
                  '<div class="promo-product-link" style="cursor:pointer;padding:0.2rem 0;font-size:0.85rem;color:var(--green)">' +
                  escapeHtml(name) +
                  "</div>";
              });
              html += "</div>";
            }
            html += "</div>";
          });
          html += "</div>";
        });
        el.innerHTML = html;
        // Click to expand products
        el.querySelectorAll(".promo-card-header").forEach((h) => {
          h.addEventListener("click", () => {
            const list = h.parentElement.querySelector(".promo-card-products");
            if (list)
              list.style.display =
                list.style.display === "none" ? "block" : "none";
          });
        });
        // Store filter
        el.querySelectorAll("[data-promo-filter]").forEach((chip) => {
          chip.addEventListener("click", () => {
            el.querySelectorAll("[data-promo-filter]").forEach((c) => {
              c.classList.remove("active");
              c.setAttribute("aria-pressed", "false");
            });
            chip.classList.add("active");
            chip.setAttribute("aria-pressed", "true");
            const filter = chip.dataset.promoFilter;
            el.querySelectorAll(".promo-card").forEach((card) => {
              if (filter === "all") {
                card.style.display = "block";
                return;
              }
              const stores =
                card.querySelector(".promo-card-meta")?.textContent || "";
              card.style.display = stores.toLowerCase().includes(filter)
                ? "block"
                : "none";
            });
          });
        });
        // Product link click → switch to Products tab and search
        el.querySelectorAll(".promo-product-link").forEach((link) => {
          link.addEventListener("click", () => {
            const name = link.textContent;
            document.querySelector('[data-tab="products"]').click();
            const searchInput = document.getElementById("search-input");
            if (searchInput) {
              searchInput.value = name;
              searchInput.dispatchEvent(new Event("input"));
            }
          });
        });
      }

      function renderBrochures() {
        const el = document.getElementById("brochures-content");
        if (!el || !consolidatedData) return;
        const products = consolidatedData.products || [];
        const singles = consolidatedData.singles || [];
        const all = [...products, ...singles];
        const brochures = {};
        all.forEach((item) => {
          const stores = item.stores || [item];
          (Array.isArray(stores) ? stores : [stores]).forEach((se) => {
            const img = se.image_path || item.image_path;
            if (!img) return;
            if (!brochures[img])
              brochures[img] = {
                image_path: img,
                store: se.store || item.store,
                products: [],
                count: 0,
              };
            brochures[img].count++;
            if (brochures[img].products.length < 10)
              brochures[img].products.push(item);
          });
        });
        if (!Object.keys(brochures).length) {
          el.innerHTML =
            '<div class="empty-box"><h3>No brochures available</h3><p>Brochure images will appear here once products have associated brochure images.</p></div>';
          return;
        }
        const storeGroups = {};
        Object.values(brochures).forEach((b) => {
          const dateMatch = b.image_path.match(/\/(\d{4})(\d{2})(\d{2})\//);
          const dateStr = dateMatch
            ? `${dateMatch[1]}-${dateMatch[2]}-${dateMatch[3]}`
            : "Unknown date";
          if (!storeGroups[b.store]) storeGroups[b.store] = {};
          if (!storeGroups[b.store][dateStr])
            storeGroups[b.store][dateStr] = [];
          storeGroups[b.store][dateStr].push(b);
        });
        let html = '<div class="filter-chips" style="margin-bottom:1rem">';
        html +=
          '<button class="chip active" data-brochure-filter="all" aria-pressed="true">All</button>';
        html +=
          '<button class="chip" data-brochure-filter="Lotte" aria-pressed="false">Lotte</button>';
        html +=
          '<button class="chip" data-brochure-filter="Superindo" aria-pressed="false">Superindo</button>';
        html += "</div>";
        Object.keys(storeGroups)
          .sort()
          .forEach((storeName) => {
            html +=
              '<div class="brochure-store-group" data-brochure-store="' +
              escapeAttr(storeName) +
              '">';
            html += '<h3 class="promo-type-header">' + escapeHtml(storeName) + "</h3>";
            Object.keys(storeGroups[storeName])
              .sort()
              .reverse()
              .forEach((dateStr) => {
                html +=
                  '<h4 style="font-size:0.82rem;color:var(--gray-700);margin:0.5rem 0 0.3rem">' +
                  escapeHtml(dateStr) +
                  "</h4>";
                html += '<div class="brochure-grid">';
                storeGroups[storeName][dateStr].forEach((b) => {
                  html += '<div class="brochure-card">';
                  html +=
                    '<div class="brochure-img-wrap" style="cursor:pointer">';
                  html +=
                    '<img src="' +
                    escapeAttr(safeUrl(b.image_path)) +
                    '" alt="' +
                    escapeAttr(b.store) +
                    ' brochure" loading="lazy" style="width:100%;border-radius:var(--radius-sm);aspect-ratio:3/4;object-fit:cover;background:var(--gray-100)" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">';
                  html +=
                    '<div class="brochure-fallback" style="display:none;width:100%;border-radius:var(--radius-sm);aspect-ratio:3/4;align-items:center;justify-content:center;font-size:0.75rem;color:var(--gray-700);background:var(--gray-100)">' +
                    escapeHtml(b.store) +
                    " (" +
                    escapeHtml(b.count) +
                    " products)</div>";
                  html +=
                    '<div style="margin-top:0.3rem;font-size:0.78rem;color:var(--gray-700);font-weight:500">' +
                    escapeHtml(b.store) +
                    ' <span style="color:var(--gray-700);font-weight:400">(' +
                    escapeHtml(b.count) +
                    ")</span></div>";
                  html += "</div>";
                  html +=
                    '<div class="brochure-products" style="display:none;margin-top:0.5rem;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:0.5rem">';
                  b.products.forEach((item) => {
                    const normalized = normalizeProduct(item);
                    html +=
                      normalized.stores.length > 1
                        ? buildMatchedCard(item)
                        : buildSingleCard(item);
                  });
                  html += "</div></div>";
                });
                html += "</div>";
              });
            html += "</div>";
          });
        el.innerHTML = html;
        el.querySelectorAll(".brochure-img-wrap").forEach((wrap) => {
          wrap.addEventListener("click", () => {
            const products = wrap.nextElementSibling;
            if (products)
              products.style.display =
                products.style.display === "none" ? "grid" : "none";
          });
        });
        el.querySelectorAll(".brochure-products .product-card").forEach(
          (card) => {
            card.addEventListener("click", () => {
              const key = card.dataset.key;
              document.querySelector('[data-tab="products"]').click();
              setTimeout(() => expandCard(key), 100);
            });
            card.addEventListener("keydown", (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                document.querySelector('[data-tab="products"]').click();
                setTimeout(() => expandCard(card.dataset.key), 100);
              }
            });
          },
        );
        el.querySelectorAll("[data-brochure-filter]").forEach((chip) => {
          chip.addEventListener("click", () => {
            el.querySelectorAll("[data-brochure-filter]").forEach((c) => {
              c.classList.remove("active");
              c.setAttribute("aria-pressed", "false");
            });
            chip.classList.add("active");
            chip.setAttribute("aria-pressed", "true");
            const filter = chip.dataset.brochureFilter;
            el.querySelectorAll(".brochure-store-group").forEach((group) => {
              group.style.display =
                filter === "all" || group.dataset.brochureStore === filter
                  ? "block"
                  : "none";
            });
          });
        });
      }

      // Tab navigation
      document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
          if (tab.classList.contains("active")) return;
          document
            .querySelectorAll(".tab")
            .forEach((t) => {
              t.classList.remove("active");
              t.setAttribute("aria-selected", "false");
              t.setAttribute("tabindex", "-1");
            });
          document
            .querySelectorAll(".tab-view")
            .forEach((v) => v.classList.remove("active"));
          tab.classList.add("active");
          tab.setAttribute("aria-selected", "true");
          tab.setAttribute("tabindex", "0");
          const view = document.getElementById("view-" + tab.dataset.tab);
          if (view) view.classList.add("active");
          if (tab.dataset.tab === "promos") {
            renderPromos();
          }
          if (tab.dataset.tab === "brochures") {
            renderBrochures();
          }
        });
        tab.addEventListener("keydown", (e) => {
          const tabs = Array.from(document.querySelectorAll(".tab"));
          const idx = tabs.indexOf(tab);
          let newIdx = -1;
          switch (e.key) {
            case "ArrowLeft":
              newIdx = (idx - 1 + tabs.length) % tabs.length;
              break;
            case "ArrowRight":
              newIdx = (idx + 1) % tabs.length;
              break;
            case "Home":
              newIdx = 0;
              break;
            case "End":
              newIdx = tabs.length - 1;
              break;
            default:
              return;
          }
          e.preventDefault();
          tabs[newIdx].focus();
          tabs[newIdx].click();
        });
      });

      (function () {
        var link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = "https://fonts.googleapis.com/css2?family=DM+Mono&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap";
        document.head.appendChild(link);
      })();

      loadData();
      startAutoRefresh();

      if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("sw.js");
      }

