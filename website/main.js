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
      if (!asset) continue;
      button.href = asset.browser_download_url;
      button.removeAttribute('target');   // the file downloads; without a file, the release page opens in a new tab
      button.dataset.direct = 'yes';
    }
  })
  .catch(() => {});

// Lightbox: the steps' images with their titles and texts, one at a time.
const lightbox = document.getElementById('lightbox');
const steps = [...document.querySelectorAll('.step')];
const shown = {
  image: lightbox.querySelector('img'),
  title: lightbox.querySelector('h3'),
  text: lightbox.querySelector('figcaption p'),
  position: lightbox.querySelector('figcaption span'),
};
let current = 0;

function showStep(index) {
  current = (index + steps.length) % steps.length;
  const step = steps[current];
  const image = step.querySelector('img');
  shown.image.src = image.src;
  shown.image.alt = image.alt;
  shown.title.textContent = `Step ${current + 1}: ${step.querySelector('h3').textContent}`;
  shown.text.innerHTML = step.querySelector('p').innerHTML;
  shown.position.textContent = `${current + 1} of ${steps.length}`;
}

steps.forEach((step, index) => {
  step.querySelector('.shot-button').addEventListener('click', () => {
    showStep(index);
    lightbox.showModal();
  });
});
lightbox.querySelector('.lightbox-prev').addEventListener('click', () => showStep(current - 1));
lightbox.querySelector('.lightbox-next').addEventListener('click', () => showStep(current + 1));
lightbox.querySelector('.lightbox-close').addEventListener('click', () => lightbox.close());
lightbox.addEventListener('click', (event) => { if (event.target === lightbox) lightbox.close(); });
lightbox.addEventListener('keydown', (event) => {
  if (event.key === 'ArrowLeft') showStep(current - 1);
  if (event.key === 'ArrowRight') showStep(current + 1);
});

// First-start help: opens with a download, or from the link; one tab per system.
const help = document.getElementById('help');
const helpTitle = help.querySelector('.help-title');
function showHelp(title, system) {
  helpTitle.textContent = title;
  for (const tab of help.querySelectorAll('[data-tab]')) tab.setAttribute('aria-selected', String(tab.dataset.tab === system));
  for (const panel of help.querySelectorAll('[data-panel]')) panel.hidden = panel.dataset.panel !== system;
  if (!help.open) help.showModal();
}
const OPENING = 'Opening the app the first time';
for (const tab of help.querySelectorAll('[data-tab]')) {
  tab.addEventListener('click', () => showHelp(helpTitle.textContent, tab.dataset.tab));
}
for (const button of document.querySelectorAll('.dl')) {
  button.addEventListener('click', () => {
    showHelp(button.dataset.direct ? 'Your download has started' : OPENING, button.dataset.help);
  });
}
document.querySelector('[data-open-help]').addEventListener('click', () => {
  showHelp(OPENING, /Win/.test(navigator.userAgent) ? 'windows' : 'mac');
});
// A click outside the popup closes it.
help.addEventListener('click', (event) => {
  if (event.target !== help) return;   // also keeps keyboard clicks, which have no position, from closing it
  const box = help.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) help.close();
});
