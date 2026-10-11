import assert from 'node:assert/strict';
import test from 'node:test';
import {request} from '../web/api.mjs';

function mockResponse(status, body, json = true) {
  return {ok: status >= 200 && status < 300, status,
    json: async () => {if (!json) throw new SyntaxError('Not JSON'); return body;}};
}

test('large-import proxy rejection reports HTTP 413 without exposing the response body', async () => {
  globalThis.fetch = async () => mockResponse(413, '<html>private proxy content</html>', false);
  await assert.rejects(request('/imports/preview'), error => error.message.includes('HTTP 413') && !error.message.includes('private proxy content'));
});

test('plain-text backend error reports the failing import step and status', async () => {
  globalThis.fetch = async () => mockResponse(500, 'private server traceback', false);
  await assert.rejects(request('/imports/example/commit'), error => error.message.includes('HTTP 500') && error.message.includes('/imports/example/commit') && !error.message.includes('traceback'));
});

test('HTML login response is not reported as a successful import', async () => {
  globalThis.fetch = async () => mockResponse(200, '<html>login</html>', false);
  await assert.rejects(request('/imports/preview'), /HTTP 200/);
});

test('JSON server error preserves its support reference', async () => {
  globalThis.fetch = async () => mockResponse(500, {detail: 'Chyba serveru', request_id: 'example-reference'});
  await assert.rejects(request('/imports/preview'), /example-reference/);
});

test('valid JSON import results are unchanged', async () => {
  let sent;
  globalThis.fetch = async (path, options) => {sent = {path,options}; return mockResponse(200,{id:'staging-id',counts:{vehicles:31}});};
  const body = '{"vehicles":[]}';
  const result = await request('/imports/preview',{method:'POST',body});
  assert.equal(result.id, 'staging-id');
  assert.equal(sent.path,'/api/imports/preview');
  assert.equal(sent.options.body,body);
  assert.equal(sent.options.credentials,'same-origin');
});

test('expired application session returns to login while failed login does not recurse', async () => {
  let calls = 0;
  globalThis.fetch = async () => mockResponse(401, {detail:'Přihlaste se'});
  await assert.rejects(request('/imports/preview',{},async () => {calls++;}),/Přihlaste se/);
  await assert.rejects(request('/auth/login',{},async () => {calls++;}),/Přihlaste se/);
  assert.equal(calls,1);
});

test('network failure has an actionable message', async () => {
  globalThis.fetch = async () => {throw new TypeError('Failed to fetch');};
  await assert.rejects(request('/imports/preview'),/Server nelze kontaktovat/);
});
