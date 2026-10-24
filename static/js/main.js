// kararsızım — sayfa yenilemeden oy verme ve form iyileştirmeleri.
// Tüm akışlar JS olmadan da (form POST + yönlendirme) çalışır; burası yalnızca iyileştirmedir.
(function () {
  "use strict";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function setStatus(card, text, kind) {
    var status = card.querySelector(".poll-status");
    if (!status) return;
    status.textContent = text;
    status.className = "poll-status" + (kind ? " is-" + kind : "");
  }

  // --- Oy verme -----------------------------------------------------------

  // Parçalı dağılım çubuğu: şablondaki .dist-fill ile aynı yapı.
  function buildDistFill(data) {
    var fill = el("div", "dist-fill");
    data.results.forEach(function (item) {
      if (!item.votes) return;
      var segment = el("span", "seg opt-" + item.position);
      segment.style.flexGrow = String(item.votes);
      fill.appendChild(segment);
    });
    return fill;
  }

  // Seçenek listesi: şablondaki .legend ile aynı yapı.
  function buildLegend(data) {
    var list = el("ul", "legend");
    list.tabIndex = -1;
    data.results.forEach(function (item) {
      var row = el("li", "legend-item opt-" + item.position);
      row.appendChild(el("span", "dot"));

      var text = el("span", "legend-text", item.text + " ");
      if (item.option_id === data.voted_option_id) {
        var mine = el("span", "mine", "✓ ");
        mine.title = "Senin oyun";
        mine.appendChild(el("span", "sr-only", "Senin oyun"));
        text.appendChild(mine);
      }
      var percent = el("span", "legend-percent", "%" + item.percent + " ");
      percent.appendChild(el("span", "muted", "(" + item.votes + ")"));

      row.appendChild(text);
      row.appendChild(percent);
      list.appendChild(row);
    });
    return list;
  }

  function showResults(card, form, data) {
    var dist = card.querySelector(".dist");
    if (dist && data.total) {
      dist.textContent = "";
      dist.appendChild(buildDistFill(data));
    }
    var verdict = card.querySelector(".poll-verdict");
    if (verdict) verdict.textContent = data.status_label || "";

    if (data.closed) card.classList.add("is-closed");

    // Anket sahibinin kartında sonuçlar oy öncesi de görünür: mevcut listeyi güncelle, formu kaldır.
    var legend = buildLegend(data);
    var existing = card.querySelector(".legend");
    if (existing) {
      existing.replaceWith(legend);
      form.remove();
    } else {
      form.replaceWith(legend);
    }
    var total = card.querySelector(".js-total");
    if (total) total.textContent = data.total + " kişi oy verdi";
    legend.focus({ preventScroll: true });
  }

  function setBusy(form, busy) {
    Array.prototype.forEach.call(form.querySelectorAll("button"), function (button) {
      button.disabled = busy;
    });
  }

  function handleVote(event, form) {
    var submitter = event.submitter;
    if (!submitter || !submitter.name || !window.fetch || !window.URLSearchParams) return; // normal form akışı

    event.preventDefault();
    var card = form.closest(".poll-card");
    var token = form.elements.csrfmiddlewaretoken.value;
    var body = new URLSearchParams();
    body.set(submitter.name, submitter.value);

    setStatus(card, "", "");
    setBusy(form, true);

    fetch(form.action, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": token
      },
      body: body
    })
      .then(function (response) {
        return response.json().then(
          function (data) { return { status: response.status, data: data }; },
          function () { return { status: response.status, data: null }; }
        );
      })
      .then(function (result) {
        var data = result.data;
        if (data && data.results && (result.status === 200 || result.status === 409)) {
          showResults(card, form, data);
          if (result.status === 409) setStatus(card, data.error, "info");
          return;
        }
        setBusy(form, false);
        var message = data && data.error ? data.error : "Bir sorun oluştu. Sayfayı yenileyip tekrar dene.";
        setStatus(card, message, "error");
      })
      .catch(function () {
        setBusy(form, false);
        setStatus(card, "Bağlantı kurulamadı. İnternetini kontrol edip tekrar dene.", "error");
      });
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.matches) return;
    if (form.matches(".vote-form")) {
      handleVote(event, form);
    } else if (form.matches("[data-confirm]") && !window.confirm(form.getAttribute("data-confirm"))) {
      event.preventDefault();
    }
  });

  // --- Karakter sayacı ----------------------------------------------------

  Array.prototype.forEach.call(document.querySelectorAll("input[data-counter]"), function (input) {
    var max = parseInt(input.getAttribute("data-counter"), 10);
    var counter = el("span", "char-count");
    input.insertAdjacentElement("afterend", counter);
    function update() {
      var length = input.value.length;
      counter.textContent = length + "/" + max;
      counter.classList.toggle("is-near-limit", length >= max - 10);
    }
    input.addEventListener("input", update);
    update();
  });

  // --- Seçenek ekle / kaldır ---------------------------------------------

  var MIN_OPTIONS = 2;

  Array.prototype.forEach.call(document.querySelectorAll("[data-poll-form]"), function (form) {
    var rows = Array.prototype.slice.call(form.querySelectorAll("[data-option-row]"));
    if (!rows.length) return;

    var addButton = el("button", "btn btn-ghost btn-sm add-option", "+ Seçenek ekle");
    addButton.type = "button";
    rows[rows.length - 1].insertAdjacentElement("afterend", addButton);

    function visibleRows() {
      return rows.filter(function (row) { return !row.hidden; });
    }

    function sync() {
      var visible = visibleRows();
      visible.forEach(function (row, index) {
        row.querySelector("label").textContent = "Seçenek " + (index + 1);
        row.querySelector(".remove-option").hidden = index < MIN_OPTIONS;
      });
      rows.forEach(function (row) {
        row.querySelector("input").disabled = row.hidden;
      });
      addButton.hidden = visible.length >= rows.length;
    }

    rows.forEach(function (row, index) {
      var input = row.querySelector("input");
      var remove = el("button", "remove-option", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", "Bu seçeneği kaldır");
      remove.addEventListener("click", function () {
        input.value = "";
        row.hidden = true;
        // Gizlenen satırı sona taşı ki görünen satırlar arasında boşluk kalmasın.
        rows.splice(rows.indexOf(row), 1);
        rows.push(row);
        addButton.insertAdjacentElement("beforebegin", row);
        sync();
        addButton.focus();
      });
      row.querySelector(".option-input-wrap").appendChild(remove);
      if (index >= MIN_OPTIONS && !input.value.trim()) row.hidden = true;
    });

    addButton.addEventListener("click", function () {
      var next = rows.filter(function (row) { return row.hidden; })[0];
      if (!next) return;
      next.hidden = false;
      sync();
      next.querySelector("input").focus();
    });

    sync();
  });

  // --- Bildirimler kısa süre sonra kaybolur ------------------------------

  Array.prototype.forEach.call(document.querySelectorAll(".messages .message"), function (message) {
    window.setTimeout(function () {
      message.classList.add("is-hiding");
      window.setTimeout(function () { message.remove(); }, 450);
    }, 6000);
  });
})();
