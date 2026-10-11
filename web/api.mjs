function responseError(status, path) {
  if (status === 413) return 'Přístup k webu odmítl velikost souboru (HTTP 413). Soubor lze importovat přímo v Terminálu Codespaces podle návodu.';
  if (status === 400) return 'Server odmítl požadavek (HTTP 400). Zkontrolujte nastavení adresy webu a znovu spusťte server podle návodu pro Codespaces.';
  if (status === 401 || status === 403) return `Přístup k webu nebyl povolen (HTTP ${status}). Otevřete znovu soukromý port 8000 v Codespaces a přihlaste se.`;
  if (status >= 500) return `Server při zpracování požadavku selhal (HTTP ${status}, ${path}). Zkontrolujte poslední chybové řádky v Terminálu Codespaces.`;
  return `Místo dat přišla neplatná odpověď (HTTP ${status}, ${path}). Otevřete web znovu přes port 8000 v Codespaces.`;
}

export async function request(path, options = {}, onUnauthorized = async () => {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      headers: {'Content-Type': 'application/json', ...options.headers},
      credentials: 'same-origin',
    });
  } catch {
    throw new Error('Server nelze kontaktovat. Zkontrolujte, že běží a port 8000 je otevřený v Codespaces.');
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(responseError(response.status, path));
  }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) await onUnauthorized();
    const detail = body && typeof body.detail === 'string' ? body.detail : null;
    const reference = body && typeof body.request_id === 'string' ? ` Kód chyby: ${body.request_id}.` : '';
    throw new Error((detail || (response.status >= 500 ? responseError(response.status, path) : 'Zkontrolujte vyplněné údaje.')) + reference);
  }
  if (body === null || typeof body !== 'object') throw new Error(responseError(response.status, path));
  return body;
}
