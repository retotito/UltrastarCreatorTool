// The download links in the page are for the current release. Newer releases have other file names, so they are
// looked up; without an answer (offline, rate limit) the links in the page still work. No published release at all
// (404): nothing can be downloaded, so a click only opens the popup.
const PATTERNS = { 'mac-arm': /aarch64\.dmg$/, 'mac-intel': /(x86_64|x64)\.dmg$/, windows: /\.msi$/ };
let nothingPublished = false;

fetch('https://api.github.com/repos/retotito/UltrastarCreatorTool/releases/latest')
  .then((response) => {
    nothingPublished = response.status === 404;
    return response.ok ? response.json() : null;
  })
  .then((release) => {
    if (!release) return;
    document.getElementById('version').textContent = release.tag_name.replace(/^v/, '');
    for (const button of document.querySelectorAll('.dl')) {
      const asset = release.assets.find((a) => PATTERNS[button.dataset.file].test(a.name));
      if (asset) button.href = asset.browser_download_url;
    }
  })
  .catch(() => {});

// Highlight the visitor's system. Both Mac buttons: a browser can't tell Apple Silicon from Intel.
const system = /Mac/.test(navigator.userAgent) ? 'mac' : /Win/.test(navigator.userAgent) ? 'windows' : null;
for (const button of document.querySelectorAll(`.dl[data-os="${system}"]`)) button.classList.add('mine');

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
  button.addEventListener('click', (event) => {
    if (nothingPublished) event.preventDefault();
    showHelp(nothingPublished ? 'This download is not available yet' : 'Your download has started', button.dataset.help);
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
