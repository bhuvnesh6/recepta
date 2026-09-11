// Shared dashboard interactivity: notification polling, modal open/close helpers.

async function pollNotifications() {
  try {
    const res = await fetch('/api/notifications');
    if (!res.ok) return;
    const data = await res.json();
    const badge = document.getElementById('nav-unread-badge');
    const dot = document.getElementById('topbar-unread-dot');
    if (badge) {
      if (data.unread_count > 0) {
        badge.style.display = 'inline-flex';
        badge.textContent = data.unread_count > 9 ? '9+' : data.unread_count;
      } else {
        badge.style.display = 'none';
      }
    }
    if (dot) dot.style.display = data.unread_count > 0 ? 'block' : 'none';
  } catch (e) { /* silent - notifications are best-effort */ }
}

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('open');
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

document.addEventListener('click', (e) => {
  if (e.target.classList && e.target.classList.contains('modal-backdrop')) {
    e.target.classList.remove('open');
  }
});

document.addEventListener('DOMContentLoaded', () => {
  pollNotifications();
  setInterval(pollNotifications, 20000);
});
