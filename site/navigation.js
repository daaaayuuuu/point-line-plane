const navigation = document.querySelector('.nav-shell');
const heroMedia = document.querySelector('.hero-media');

function updateNavigationTone() {
  // The hero gradient fades to light blue just above the first preview card.
  const lightBackgroundStart = heroMedia.getBoundingClientRect().top + window.scrollY - 120;
  const navigationCenter = window.scrollY + navigation.offsetTop + navigation.offsetHeight / 2;
  navigation.dataset.tone = navigationCenter >= lightBackgroundStart ? 'light' : 'dark';
}

window.addEventListener('scroll', updateNavigationTone, { passive: true });
window.addEventListener('resize', updateNavigationTone);
updateNavigationTone();
