/**
 * Minimal API fetch helpers.
 *
 * Goal: DRY up repeated fetch + JSON parsing while preserving
 * existing behavior in callers.
 */

(function () {
  async function apiFetchJson(url, options) {
    const response = await fetch(url, options);

    let data = null;
    try {
      data = await response.json();
    } catch (e) {
      data = null;
    }

    return {
      ok: response.ok,
      status: response.status,
      response,
      data,
    };
  }

  async function apiGetJson(url, options) {
    return apiFetchJson(url, options);
  }

  async function apiPostJson(url, body, options) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, (options && options.headers) || {});

    return apiFetchJson(
      url,
      Object.assign({}, options || {}, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      }),
    );
  }

  window.apiFetchJson = apiFetchJson;
  window.apiGetJson = apiGetJson;
  window.apiPostJson = apiPostJson;
})();
