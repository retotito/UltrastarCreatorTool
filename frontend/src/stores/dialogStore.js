import { writable } from 'svelte/store';

// Active dialog state
export const dialog = writable(null);

/**
 * Show a confirm dialog. Returns a Promise<boolean>.
 * Usage: if (await confirm('Are you sure?')) { ... }
 */
export function showConfirm(message, { title = null, confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false } = {}) {
  return new Promise(resolve => {
    dialog.set({ type: 'confirm', message, title, confirmLabel, cancelLabel, danger, resolve });
  });
}

/**
 * Show an alert dialog. Returns a Promise<void>.
 * Usage: await showAlert('Something happened');
 */
export function showAlert(message, { title = null, label = 'OK' } = {}) {
  return new Promise(resolve => {
    dialog.set({ type: 'alert', message, title, label, resolve });
  });
}
