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
  shown.title.textContent = `${step.querySelector('.step-number').textContent}: ${step.querySelector('h3').textContent}`;
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
