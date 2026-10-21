# shellcheck shell=sh
# Runs inside the installed app's sandbox (see scripts/test-installed.sh).
# There is no display, sound server or session bus in CI, so keep these checks
# headless: start the command-line interface, import modules, look for files.
set -eu

test -x /app/bin/teams-office
test -x /app/teams-office/teams-for-linux
test -f /app/teams-office/resources/app.asar
test -x /app/bin/fido2-assert

# The packaged Electron, run as Node.js against the Platform runtime, starts
# the Office add-in host and the MCP endpoint the way the app does: it makes
# a certificate with the runtime's openssl, writes both add-in manifests,
# serves an add-in file over verified HTTPS and answers an MCP handshake on
# the private socket. Signing in to Teams and live documents need a desktop.
check=$(cat <<'JS'
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const https = require('node:https');
const root = '/app/teams-office/resources/app.asar';
const { startAddinHost } = require(`${root}/app/office/addinHost`);
const { startLocalEndpoint } = require(`${root}/app/mcp/localEndpoint`);
const { createOfficeMcpServer } = require(`${root}/app/mcp/server`);
const { OfficeInspector } = require(`${root}/app/office/inspector`);

async function main() {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'office-check-'));
  let host;
  let endpoint;
  try {
    const mcpDirectory = path.join(directory, 'mcp');
    await fs.mkdir(mcpDirectory, { mode: 0o700 });
    // Exercises the runtime's openssl executable, key generation and HTTPS.
    host = await startAddinHost({ directory: mcpDirectory, port: 0 });
    for (const [file, api] of [[host.manifestPath, 'ExcelApi'], [host.wordManifestPath, 'WordApi']]) {
      assert.match(await fs.readFile(file, 'utf8'), new RegExp(api));
    }
    const cert = await fs.readFile(path.join(mcpDirectory, 'addin/localhost.pem'));
    await new Promise((resolve, reject) => {
      const request = https.get(`${host.origin}/wordOperations.js`, { ca: cert }, (response) => {
        assert.equal(response.statusCode, 200);
        response.resume();
        response.on('end', resolve);
        response.on('error', reject);
      });
      request.setTimeout(5000, () => request.destroy(new Error('HTTPS timeout')));
      request.on('error', reject);
    });
    endpoint = await startLocalEndpoint({ directory: mcpDirectory,
      createServer: () => createOfficeMcpServer(new OfficeInspector(() => []), { listDocuments: async () => ({ documents: [] }) }),
    });
    assert.equal((await fs.stat(endpoint.socketPath)).mode & 0o777, 0o600);
    await new Promise((resolve, reject) => {
      const socket = net.createConnection(endpoint.socketPath);
      let buffer = '';
      socket.setTimeout(5000, () => socket.destroy(new Error('MCP timeout')));
      socket.on('error', reject);
      socket.on('connect', () => socket.write(`${JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: {
        protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'flatpak-check', version: '1' },
      } })}\n`));
      socket.on('data', (chunk) => {
        buffer += chunk;
        if (!buffer.includes('\n')) return;
        try {
          assert.equal(JSON.parse(buffer.split('\n')[0]).result.serverInfo.name, 'teams-for-linux-office');
          socket.destroy();
          resolve();
        } catch (error) { socket.destroy(); reject(error); }
      });
    });
    console.log('Installed Flatpak: certificates, add-in assets and MCP handshake passed.');
  } finally {
    await endpoint?.close();
    await host?.close();
    await fs.rm(directory, { recursive: true, force: true });
  }
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
JS
)
ELECTRON_RUN_AS_NODE=1 /app/teams-office/teams-for-linux -e "$check"

# flatpak-builder records the license files it finds at the root of each
# module's source; the main module's must be there.
test -n "$(ls "/app/share/licenses/$FLATPAK_ID/teams-office")"

echo 'Installed app checks passed.'
