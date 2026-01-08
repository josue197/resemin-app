
// ==== CONFIGURACIÓN ====
// En producción: const API = "https://tu-backend.railway.app";
const API = "https://resemin-app.onrender.com";

// Estado admin
let ADMIN = JSON.parse(sessionStorage.getItem("ADMIN_CRED") || "null");

// ===== Tema (noche/día) RESILIENTE =====
function applyTheme(theme) {
  try {
    const t = theme || localStorage.getItem("THEME") || "light";
    document.documentElement.setAttribute("data-theme", t);
    localStorage.setItem("THEME", t);

    const toggle = document.getElementById("theme-toggle");
    if (!toggle) return;

    const icon = toggle.querySelector("i");
    const label = toggle.querySelector("span");
    if (t === "dark") {
      if (icon) icon.className = "bi bi-sun";
      if (label) label.textContent = "Modo día";
    } else {
      if (icon) icon.className = "bi bi-moon";
      if (label) label.textContent = "Modo noche";
    }
  } catch (err) {
    console.warn("applyTheme error:", err);
  }
}

// ==== Utilidades ====
function showAlert(el, type, text) {
  el.className = `alert alert-${type}`;
  el.textContent = text;
  el.style.display = "block";
}
function hideAlert(el) { el.style.display = "none"; }
function maybeToISODate(input) {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(input);
  if (m) { const [_, dd, mm, yyyy] = m; return `${yyyy}-${mm}-${dd}`; }
  return input;
}

// ==== Admin login modal ====
function openAdminLogin() {
  const modal = document.getElementById("admin-login-modal");
  if (modal) modal.style.display = "block";
}
function closeAdminLogin() {
  const modal = document.getElementById("admin-login-modal");
  if (modal) modal.style.display = "none";
}
async function doAdminLogin(ev) {
  ev.preventDefault();
  const user = document.getElementById("admin-user").value.trim();
  const pass = document.getElementById("admin-pass").value.trim();
  const alertBox = document.getElementById("admin-alert");
  if (!alertBox) return;
  hideAlert(alertBox);

  if (!user || !pass) { showAlert(alertBox, "warning", "Ingresa usuario y contraseña."); return; }

  try {
    const res = await fetch(`${API}/admin/login`, {
      method: "POST",
      headers: { "X-Admin-User": user, "X-Admin-Password": pass, "Accept": "application/json" }
    });
    if (!res.ok) { const txt = await res.text(); throw new Error(`HTTP ${res.status}: ${txt}`); }

    ADMIN = { user, pass };
    sessionStorage.setItem("ADMIN_CRED", JSON.stringify(ADMIN));
    closeAdminLogin();

    showAlert(alertBox, "success", "Login correcto.");
    const panel = document.getElementById("admin-panel");
    const btnLogin = document.getElementById("admin-login-btn");
    const btnLogout = document.getElementById("admin-logout-btn");
    if (panel) panel.style.display = "block";
    if (btnLogin) btnLogin.style.display = "none";
    if (btnLogout) btnLogout.style.display = "inline-block";
  } catch (e) {
    showAlert(alertBox, "danger", `Error de login: ${e.message}`);
  }
}
function doAdminLogout() {
  ADMIN = null;
  sessionStorage.removeItem("ADMIN_CRED");
  const panel = document.getElementById("admin-panel");
  const btnLogin = document.getElementById("admin-login-btn");
  const btnLogout = document.getElementById("admin-logout-btn");
  if (panel) panel.style.display = "none";
  if (btnLogin) btnLogin.style.display = "inline-block";
  if (btnLogout) btnLogout.style.display = "none";
}

// ==== Admin upload & config ====
const visibleSet = new Set();
function toggleVisible(col) { if (visibleSet.has(col)) visibleSet.delete(col); else visibleSet.add(col); }
function selectAll() { document.querySelectorAll("#columns-list input[type='checkbox']").forEach(cb => { cb.checked = true; visibleSet.add(cb.value); }); }
function clearAll() { document.querySelectorAll("#columns-list input[type='checkbox']").forEach(cb => { cb.checked = false; }); visibleSet.clear(); }

async function uploadExcel(ev) {
  ev.preventDefault();
  const alertBox = document.getElementById("admin-alert");
  const fileInput = document.getElementById("excel-file");
  const columnsList = document.getElementById("columns-list");
  const dniSel = document.getElementById("dni-col");
  const fechaSel = document.getElementById("fecha-col");
  if (!alertBox) return;

  hideAlert(alertBox);
  if (columnsList) columnsList.innerHTML = "";
  if (dniSel) dniSel.innerHTML = `<option value="">-- elegir --</option>`;
  if (fechaSel) fechaSel.innerHTML = `<option value="">-- elegir --</option>`;

  if (!ADMIN) { showAlert(alertBox, "warning", "Primero inicia sesión como Admin."); return; }
  if (!fileInput || !fileInput.files[0]) { showAlert(alertBox, "warning", "Selecciona un archivo Excel."); return; }

  try {
    showAlert(alertBox, "info", "Subiendo Excel...");
    const form = new FormData();
    form.append("file", fileInput.files[0]);

    const res = await fetch(`${API}/admin/upload`, {
      method: "POST",
      headers: { "X-Admin-User": ADMIN.user, "X-Admin-Password": ADMIN.pass, "Accept": "application/json" },
      body: form
    });
    if (!res.ok) { const txt = await res.text(); throw new Error(`HTTP ${res.status}: ${txt}`); }

    const data = await res.json();
    const columns = data.columns || [];
    if (columnsList) {
      const html = columns.map(col => `
        <label class="form-check me-3 mb-2">
          <input class="form-check-input" type="checkbox" value="${col}" id="col-${col}" onchange="toggleVisible('${col}')">
          <span class="form-check-label">${col}</span>
        </label>
      `).join("");
      columnsList.innerHTML = html;
    }
    if (dniSel)   dniSel.innerHTML   += columns.map(c => `<option value="${c}">${c}</option>`).join("");
    if (fechaSel) fechaSel.innerHTML += columns.map(c => `<option value="${c}">${c}</option>`).join("");

    showAlert(alertBox, "success", `Excel subido. Columnas: ${columns.length}`);
  } catch (e) {
    showAlert(alertBox, "danger", `Error subiendo Excel: ${e.message}`);
  }
}

async function saveConfig(ev) {
  ev.preventDefault();
  const alertBox = document.getElementById("admin-alert");
  const dniCol = document.getElementById("dni-col")?.value.trim();
  const fechaCol = document.getElementById("fecha-col")?.value.trim();
  if (!alertBox) return;

  hideAlert(alertBox);
  if (!ADMIN) { showAlert(alertBox, "warning", "Primero inicia sesión como Admin."); return; }
  if (!dniCol || !fechaCol) { showAlert(alertBox, "warning", "Selecciona columnas DNI y Fecha."); return; }
  if (visibleSet.size === 0) { showAlert(alertBox, "warning", "Selecciona al menos una columna visible."); return; }

  const payload = { dni_column: dniCol, fecha_column: fechaCol, visible_columns: Array.from(visibleSet) };

  try {
    showAlert(alertBox, "info", "Guardando configuración...");
    const res = await fetch(`${API}/admin/config`, {
      method: "POST",
      headers: {
        "X-Admin-User": ADMIN.user,
        "X-Admin-Password": ADMIN.pass,
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify(payload)
    });
    if (!res.ok) { const txt = await res.text(); throw new Error(`HTTP ${res.status}: ${txt}`); }
    showAlert(alertBox, "success", "Configuración guardada correctamente.");
  } catch (e) {
    showAlert(alertBox, "danger", `Error guardando configuración: ${e.message}`);
  }
}

// ==== Consulta pública ====
async function consultarSubmit(ev) {
  ev.preventDefault();
  const dni = document.getElementById("dni")?.value.trim();
  let fecha = document.getElementById("fecha")?.value.trim();
  const alertBox = document.getElementById("consulta-alert");
  const resultBox = document.getElementById("resultado");
  if (!alertBox || !resultBox) return;

  hideAlert(alertBox);
  resultBox.innerHTML = "";
  if (!dni || !fecha) { showAlert(alertBox, "warning", "Completa DNI y Fecha."); return; }

  fecha = maybeToISODate(fecha);

  try {
    showAlert(alertBox, "info", "Consultando...");
    const url = new URL(`${API}/public/query`);
    url.searchParams.set("dni", dni);
    url.searchParams.set("fecha", fecha);

    const res = await fetch(url, { headers: { "Accept": "application/json" }});
    if (!res.ok) { const txt = await res.text(); throw new Error(`HTTP ${res.status}: ${txt}`); }
    const data = await res.json();

    if (!data.found) { showAlert(alertBox, "danger", data.message || "No encontrado"); return; }
    hideAlert(alertBox);

    renderResultado(data);
  } catch (e) {
    showAlert(alertBox, "danger", `Error: ${e.message}`);
  }
}

// ==== Render resultado (múltiples periodos) ====
function renderResultado(data) {
  const contenedor = document.getElementById('resultado');
  contenedor.innerHTML = '';

  const resultados = data.results || [];
  if (!Array.isArray(resultados) || resultados.length === 0) {
    contenedor.innerHTML = '<div class="alert alert-info">No se encontraron registros.</div>';
    return;
  }

  // Cabecera con DNI y Nombre
  const persona = resultados[0];
  contenedor.insertAdjacentHTML('beforeend', `
    <div class="card mb-3">
      <div class="card-body">
        <div class="row">
          <div class="col-12 col-md-6"><strong>DNI:</strong> ${persona.DNI ?? '-'}</div>
          <div class="col-12 col-md-6"><strong>Apellidos y Nombres:</strong> ${persona.APELLIDOS_NOMBRES ?? '-'}</div>
        </div>
      </div>
    </div>
  `);

  // Tabla con todos los periodos
  const tbody = resultados.map(r => `
    <tr>
      <td>${r.PERIODO_VACACIONAL ?? '-'}</td>
      <td>${r.FECHA_INGRESO ?? '-'}</td>
      <td>${r.DIAS_PENDIENTES ?? '-'}</td>
      <td>${r.VENCIMIENTO ?? '-'}</td>
      <td>${r.OBSERVACION ?? '-'}</td>
    </tr>
  `).join('');

  contenedor.insertAdjacentHTML('beforeend', `
    <table class="table table-sm table-striped">
      <thead>
        <tr>
          <th>Periodo</th>
          <th>Fecha ingreso</th>
          <th>Días pendientes</th>
          <th>Vencimiento</th>
          <th>Observación</th>
        </tr>
      </thead>
      <tbody>${tbody}</tbody>
    </table>
  `);
}

// ==== INIT RESILIENTE ====
document.addEventListener("DOMContentLoaded", () => {
  applyTheme();
  const toggle = document.getElementById("theme-toggle");
  if (toggle) toggle.addEventListener("click", () => {
    const curr = document.documentElement.getAttribute("data-theme") || "light";
    applyTheme(curr === "dark" ? "light" : "dark");
  });

  document.getElementById("admin-login-btn")?.addEventListener("click", openAdminLogin);
  document.getElementById("admin-logout-btn")?.addEventListener("click", doAdminLogout);

  document.getElementById("admin-login-form")?.addEventListener("submit", doAdminLogin);
  document.getElementById("upload-form")?.addEventListener("submit", uploadExcel);
  document.getElementById("config-form")?.addEventListener("submit", saveConfig);
  document.getElementById("btn-select-all")?.addEventListener("click", selectAll);
  document.getElementById("btn-clear-all")?.addEventListener("click", clearAll);

  document.getElementById("consulta-form")?.addEventListener("submit", consultarSubmit);

  if (ADMIN) {
    const panel = document.getElementById("admin-panel");
    const btnLogin = document.getElementById("admin-login-btn");
    const btnLogout = document.getElementById("admin-logout-btn");
    if (panel) panel.style.display = "block";
    if (btnLogin) btnLogin.style.display = "none";
    if (btnLogout) btnLogout.style.display = "inline-block";
  }
});
