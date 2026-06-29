
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

      let reviewItems = [];
      let decisions = {};
      let currentFilter = "pending";

      const STORE_COLORS = { lotte: "#0057A8", superindo: "#E8211D" };
      const STORE_NAMES = { lotte: "Lotte Mart", superindo: "Superindo" };

      function formatDate(iso) {
        if (!iso) return "";
        const d = new Date(iso);
        const months = [
          "Jan",
          "Feb",
          "Mar",
          "Apr",
          "May",
          "Jun",
          "Jul",
          "Aug",
          "Sep",
          "Oct",
          "Nov",
          "Dec",
        ];
        return (
          d.getDate() +
          " " +
          months[d.getMonth()] +
          " " +
          d.getFullYear() +
          " " +
          d.getHours().toString().padStart(2, "0") +
          ":" +
          d.getMinutes().toString().padStart(2, "0")
        );
      }

      function getStoreKey(storeName) {
        return (storeName || "").toLowerCase().replace(/\s+/g, "");
      }

      function loadDecisions() {
        try {
          decisions = JSON.parse(
            localStorage.getItem("haqita_review_decisions") || "{}",
          );
        } catch {
          decisions = {};
        }
      }

      function saveDecisions() {
        localStorage.setItem(
          "haqita_review_decisions",
          JSON.stringify(decisions),
        );
      }

      function makeItemKey(item) {
        const a = item.product_a?.name || "";
        const b = item.product_b?.name || "";
        return a + "|" + b + "|" + (item.detected_at || "");
      }

      function renderSummary() {
        const total = reviewItems.length;
        const approved = Object.values(decisions).filter(
          (d) => d === "approved",
        ).length;
        const rejected = Object.values(decisions).filter(
          (d) => d === "rejected",
        ).length;
        const pending = total - approved - rejected;
        document.getElementById("count-pending").textContent = pending;
        document.getElementById("count-approved").textContent = approved;
        document.getElementById("count-rejected").textContent = rejected;
      }

      function renderList() {
        const list = document.getElementById("review-list");
        const filtered = reviewItems.filter((item) => {
          const key = makeItemKey(item);
          const status = decisions[key] || "pending";
          if (currentFilter === "all") return true;
          return status === currentFilter;
        });

        if (filtered.length === 0) {
          list.innerHTML = `<div style="text-align:center;padding:2rem;color:var(--gray-700)">No ${escapeHtml(currentFilter)} items</div>`;
          return;
        }

        list.innerHTML = filtered
          .map((item) => {
            const key = makeItemKey(item);
            const status = decisions[key] || "pending";
            const a = item.product_a || {};
            const b = item.product_b || {};
            const aStoreKey = getStoreKey(a.store);
            const bStoreKey = getStoreKey(b.store);
            const aColor = STORE_COLORS[aStoreKey] || "var(--gray-300)";
            const bColor = STORE_COLORS[bStoreKey] || "var(--gray-300)";
            const aName = STORE_NAMES[aStoreKey] || a.store || "Unknown";
            const bName = STORE_NAMES[bStoreKey] || b.store || "Unknown";

            return `<div class="review-item status-${escapeHtml(status)}">
      <div class="review-header">
        <span class="review-reason">${escapeHtml(item.reason || "unknown")}</span>
        <span class="review-time">${escapeHtml(formatDate(item.detected_at))}</span>
      </div>
      <div class="product-compare">
        <div class="product-col">
          <div><span class="store-dot" style="background:${escapeHtml(aColor)}"></span><span class="name">${escapeHtml(a.name || "Unknown")}</span></div>
          <div class="meta">${escapeHtml(a.brand || "")} ${escapeHtml(a.unit || "")}</div>
          <div class="price">${a.price ? escapeHtml("Rp " + a.price.toLocaleString("id-ID")) : "-"}</div>
          <div class="meta">${escapeHtml(aName)}</div>
        </div>
        <div class="compare-arrow">↔</div>
        <div class="product-col">
          <div><span class="store-dot" style="background:${escapeHtml(bColor)}"></span><span class="name">${escapeHtml(b.name || "Unknown")}</span></div>
          <div class="meta">${escapeHtml(b.brand || "")} ${escapeHtml(b.unit || "")}</div>
          <div class="price">${b.price ? escapeHtml("Rp " + b.price.toLocaleString("id-ID")) : "-"}</div>
          <div class="meta">${escapeHtml(bName)}</div>
        </div>
      </div>
      <div class="review-actions" data-key="${escapeAttr(key)}">
        ${
          status === "pending"
            ? `
          <button class="btn btn-approve" data-decision="approved">Approve Match</button>
          <button class="btn btn-reject" data-decision="rejected">Reject Match</button>
        `
            : `
          <span style="font-size:0.85rem;color:${status === "approved" ? "var(--green)" : "var(--red)"};margin-right:auto;padding:0.45rem 0">
            ${status === "approved" ? "✓ Approved" : "✗ Rejected"}
          </span>
          <button class="btn btn-undo" data-decision="undo">Undo</button>
        `
        }
      </div>
    </div>`;
          })
          .join("");
      }

      function setDecision(key, decision) {
        if (decision) {
          decisions[key] = decision;
        } else {
          delete decisions[key];
        }
        saveDecisions();
        renderSummary();
        renderList();
      }

      document.getElementById("review-list").addEventListener("click", (e) => {
        const btn = e.target.closest("[data-decision]");
        if (!btn) return;
        const actions = btn.closest(".review-actions");
        if (!actions) return;
        const key = actions.dataset.key;
        const decision = btn.dataset.decision;
        if (decision === "undo") {
          setDecision(key, null);
        } else {
          setDecision(key, decision);
        }
      });

      document.querySelectorAll(".filter-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          document
            .querySelectorAll(".filter-btn")
            .forEach((b) => {
              b.classList.remove("active");
              b.setAttribute("aria-pressed", "false");
            });
          btn.classList.add("active");
          btn.setAttribute("aria-pressed", "true");
          currentFilter = btn.dataset.filter;
          renderList();
        });
      });

      document.getElementById("btn-export").addEventListener("click", () => {
        const output = Object.entries(decisions).map(([key, decision]) => {
          const [nameA, nameB, detectedAt] = key.split("|");
          return {
            product_a: nameA,
            product_b: nameB,
            detected_at: detectedAt,
            decision,
          };
        });
        const blob = new Blob([JSON.stringify(output, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "review_decisions.json";
        a.click();
        URL.revokeObjectURL(url);
      });

      document.getElementById("btn-clear").addEventListener("click", () => {
        if (confirm("Clear all review decisions? This cannot be undone.")) {
          decisions = {};
          saveDecisions();
          renderSummary();
          renderList();
        }
      });

      async function loadData() {
        try {
          const res = await fetch("output/html/review_queue.json");
          if (!res.ok) throw new Error("Failed to fetch review queue");
          const data = await res.json();
          reviewItems = Array.isArray(data) ? data : data.items || [];
          loadDecisions();
          renderSummary();
          renderList();
          document.getElementById("loading").style.display = "none";
          if (reviewItems.length === 0) {
            document.getElementById("empty-state").style.display = "block";
          } else {
            document.getElementById("app").style.display = "block";
          }
        } catch (err) {
          document.getElementById("loading").style.display = "none";
          document.getElementById("error-state").style.display = "block";
          document.getElementById("error-message").textContent = err.message;
        }
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

      if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("sw.js");
      }

