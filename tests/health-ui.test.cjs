const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('web/index.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function setup(fetch) {
    const elements = Object.fromEntries(
        ['check-server', 'result', 'server-status', 'server-value'].map(id =>
            [id, {textContent: '', disabled: false, addEventListener() {}}]));
    let timeout;
    let cleared = false;
    const context = vm.createContext({
        document: {getElementById: id => elements[id]}, fetch, AbortController,
        setTimeout(fn) {timeout = fn; return 1;},
        clearTimeout() {cleared = true;},
    });
    vm.runInContext(script, context);
    return {elements, check: () => context.checkHealth(), expire: () => timeout(), cleared: () => cleared};
}

test('successful check uses relative URL and updates the status', async () => {
    const ui = setup(async (url, options) => {
        assert.equal(url, '/health');
        assert.equal(options.cache, 'no-store');
        return {ok: true, json: async () => ({ok: true, service: 'Vantrix', status: 'running'})};
    });
    const pending = ui.check();
    assert.equal(ui.elements['check-server'].disabled, true);
    await pending;
    assert.equal(ui.elements['server-value'].textContent, 'Online');
    assert.equal(ui.elements.result.textContent, 'Server: running');
    assert.equal(ui.elements['check-server'].disabled, false);
    assert.equal(ui.cleared(), true);
});

for (const [name, response] of [
    ['HTTP error', async () => ({ok: false})],
    ['invalid JSON', async () => ({ok: true, json: async () => {throw Error('invalid');}})],
    ['unexpected payload', async () => ({ok: true, json: async () => ({ok: true})})],
    ['network error', async () => {throw Error('offline');}],
]) {
    test(name + ' never displays online', async () => {
        const ui = setup(response);
        await ui.check();
        assert.equal(ui.elements['server-value'].textContent, 'Unavailable');
        assert.match(ui.elements.result.textContent, /failed/);
        assert.equal(ui.elements['check-server'].disabled, false);
        assert.equal(ui.cleared(), true);
    });
}

test('timeout aborts the request and permits retry', async () => {
    const ui = setup((url, {signal}) => new Promise((resolve, reject) => {
        signal.addEventListener('abort', () => reject(Error('timeout')));
    }));
    const pending = ui.check();
    ui.expire();
    await pending;
    assert.equal(ui.elements['server-value'].textContent, 'Unavailable');
    assert.equal(ui.elements['check-server'].disabled, false);
});
