// The download buttons point at the newest release's files. File names contain the version, so they are looked up;
// without an answer (offline, rate limit) the buttons keep their link to the release page.
const PATTERNS = { 'mac-arm': /aarch64\.dmg$/, 'mac-intel': /(x86_64|x64)\.dmg$/, windows: /\.msi$/ };

fetch('https://api.github.com/repos/retotito/UltrastarCreatorTool/releases/latest')
  .then((response) => (response.ok ? response.json() : null))
  .then((release) => {
    if (!release) return;
    document.getElementById('version').textContent = `Version ${release.tag_name.replace(/^v/, '')} · free`;
    for (const button of document.querySelectorAll('.dl')) {
      const asset = release.assets.find((a) => PATTERNS[button.dataset.file].test(a.name));
      if (asset) button.href = asset.browser_download_url;
    }
  })
  .catch(() => {});
