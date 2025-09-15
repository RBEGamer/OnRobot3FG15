async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) throw new Error(data.error || res.statusText);
  return data;
}

async function refresh() {
  try {
    const { status } = await api('GET', '/api/status');
    document.getElementById('s-ready').textContent = status.ready;
    document.getElementById('s-open').textContent = status.open;
    document.getElementById('s-closed').textContent = status.closed;
    document.getElementById('s-gripped').textContent = status.gripped;
    document.getElementById('s-width').textContent = status.width_01mm;
    document.getElementById('s-force').textContent = status.force;
    document.getElementById('s-diam').textContent = status.diameter_01mm;
    document.getElementById('s-gt').textContent = status.grip_type;
    msg('');
  } catch (e) {
    msg('Status error: ' + e.message);
  }
}

function msg(text) {
  document.getElementById('msg').textContent = text || '';
}

async function on(id, fn) {
  document.getElementById(id).addEventListener('click', async () => {
    try {
      await fn();
      await new Promise(r => setTimeout(r, 200));
      await refresh();
      msg('');
    } catch (e) {
      msg(e.message);
    }
  });
}

on('btnOpen', () => api('POST', '/api/open'));
on('btnClose', () => api('POST', '/api/close'));
on('btnMove', () => api('POST', '/api/move'));
on('btnFlex', () => api('POST', '/api/flex'));
on('btnStop', () => api('POST', '/api/stop'));

on('btnSetForce', () => {
  const v = parseInt(document.getElementById('force').value || '0', 10);
  return api('POST', '/api/set_force', { value: v });
});
on('btnSetDiam', () => {
  const v = parseInt(document.getElementById('diam').value || '0', 10);
  return api('POST', '/api/set_diameter', { value: v });
});
on('btnSetGrip', () => {
  const v = parseInt(document.getElementById('grip').value || '0', 10);
  return api('POST', '/api/set_griptype', { value: v });
});

setInterval(refresh, 500);
refresh();

